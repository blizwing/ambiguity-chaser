"""Set-level consistency check, conflict pause, and per-branch cases.
Every model call is scripted; nothing here touches the API."""

import json
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import branches
import consistency
import graph
from schemas import Conflict, ConsistencyReport, ground_conflicts

REQS = {
    "R1": "Guest checkout sessions expire after 15 minutes of inactivity.",
    "R2": "A guest session must never expire while the cart contains items.",
    "R3": "Order totals include tax calculated on the delivery address.",
}
GOOD_CONFLICT = {
    "req_ids": ["R1", "R2"],
    "quotes": ["expire after 15 minutes of inactivity", "must never expire while the cart contains items"],
    "shared_situation": "an idle guest session with items in the cart",
    "explanation": "One expires the session, the other forbids it.",
}


def reply(payload):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(text=text, input_tokens=1, output_tokens=1, stop_reason="stop", model_name="fake")


def report(*conflicts):
    return {"conflicts": list(conflicts), "reasoning": "checked"}


# --- ground_conflicts: the code-side integrity check on the model's claim ---


def _ground(conflict):
    rep = ConsistencyReport.model_validate(report(conflict))
    return ground_conflicts(rep, REQS)


def test_verbatim_quotes_are_grounded():
    grounded, dropped = _ground(GOOD_CONFLICT)
    assert len(grounded) == 1 and not dropped


def test_whitespace_differences_do_not_break_grounding():
    spaced = {**GOOD_CONFLICT, "quotes": ["expire  after 15\nminutes of inactivity", GOOD_CONFLICT["quotes"][1]]}
    grounded, _ = _ground(spaced)
    assert len(grounded) == 1


def test_paraphrased_quote_is_dropped_with_a_reason():
    bad = {**GOOD_CONFLICT, "quotes": ["sessions time out after a quarter hour", GOOD_CONFLICT["quotes"][1]]}
    grounded, dropped = _ground(bad)
    assert not grounded
    assert "not found verbatim" in dropped[0][1] and "R1" in dropped[0][1]


def test_quote_attributed_to_the_wrong_requirement_is_dropped():
    swapped = {**GOOD_CONFLICT, "quotes": list(reversed(GOOD_CONFLICT["quotes"]))}
    grounded, dropped = _ground(swapped)
    assert not grounded and dropped


def test_unknown_id_and_repeated_id_are_dropped():
    unknown = {**GOOD_CONFLICT, "req_ids": ["R1", "R9"]}
    assert not _ground(unknown)[0]
    repeated = {**GOOD_CONFLICT, "req_ids": ["R1", "R1"]}
    assert "repeated" in _ground(repeated)[1][0][1]


def test_conflict_needs_a_shared_situation():
    with pytest.raises(ValueError):
        Conflict.model_validate({**GOOD_CONFLICT, "shared_situation": "  "})


# --- check_consistency statuses ---


def script(monkeypatch, *replies):
    queue = list(replies)
    monkeypatch.setattr(graph, "call_deepseek_json", lambda prompt, *a, **kw: reply(queue.pop(0)))


def test_grounded_conflict_gives_conflict_status(monkeypatch):
    script(monkeypatch, report(GOOD_CONFLICT))
    result = consistency.check_consistency(REQS)
    assert result.status == "conflict"
    assert [result.status_for(r) for r in REQS] == ["conflict", "conflict", "checked"]
    assert result.conflicts_for("R3") == []


def test_no_conflicts_gives_checked(monkeypatch):
    script(monkeypatch, report())
    assert consistency.check_consistency(REQS).status == "checked"


def test_ungrounded_claim_is_a_warning_not_a_conflict(monkeypatch):
    bad = {**GOOD_CONFLICT, "quotes": ["made up", "also made up"]}
    script(monkeypatch, report(bad))
    result = consistency.check_consistency(REQS)
    assert result.status == "checked"
    assert result.warnings and "dropped" in result.warnings[0]


def test_unreadable_output_is_not_checked_never_checked(monkeypatch):
    script(monkeypatch, "not json", "still not json")
    result = consistency.check_consistency(REQS)
    assert result.status == "not_checked"
    assert result.conflicts == [] and result.warnings


def test_a_single_requirement_is_not_checked_and_makes_no_call(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("no model call expected")

    monkeypatch.setattr(graph, "call_deepseek_json", boom)
    assert consistency.check_consistency({"R1": REQS["R1"]}).status == "not_checked"


# --- graph: a grounded conflict pauses, a clean or lone run does not ---

SCORE_CLEAN = {
    "has_measurable_condition": True,
    "has_vague_qualitative_language": False,
    "has_ambiguous_scope": False,
    "missing_precondition": False,
    "reasoning": "clear",
}
SPEC = {
    "title": "Session expiry",
    "description": "Verify expiry.",
    "preconditions": [],
    "test_steps": ["Idle a guest session"],
    "expected_result": "The session expires after 15 minutes.",
    "priority": "medium",
}
CONFIG = {"configurable": {"thread_id": "t1"}}


@pytest.fixture
def compiled(monkeypatch):
    def fake_json(prompt, *a, **kw):
        if "has_measurable_condition" in prompt:
            return reply(SCORE_CLEAN)
        if "matching_test_id" in prompt:
            return reply({"covered": False, "matching_test_id": None, "reasoning": "none"})
        return reply(SPEC)

    monkeypatch.setattr(graph, "call_deepseek_json", fake_json)
    monkeypatch.setattr(
        graph, "call_deepseek_with_tools", lambda *a, **kw: (SimpleNamespace(tool_calls=None), "stop")
    )
    monkeypatch.setattr(graph, "search_test_cases", lambda q: [])
    return graph.builder.compile(checkpointer=InMemorySaver())


def test_lone_run_defaults_to_not_checked_and_does_not_pause(compiled):
    result = compiled.invoke({"requirement": REQS["R1"]}, config=CONFIG)
    # LangGraph stores only fields a node or the input set, so a lone run has no
    # "consistency" key; callers read it with a default (start_run sets it explicitly).
    assert result.get("consistency", "not_checked") == "not_checked"
    assert graph.GraphState(requirement="x").consistency == "not_checked"
    assert result["status"] == "valid"


def test_conflict_pauses_with_both_quotes_then_resumes_to_a_spec(compiled):
    state = {"requirement": REQS["R1"], "consistency": "conflict", "consistency_conflicts": [GOOD_CONFLICT]}
    paused = compiled.invoke(state, config=CONFIG)

    assert paused["status"] == "needs_clarification"
    assert paused.get("test_case") is None
    question = paused["clarifying_questions"][0]
    assert all(q in question for q in GOOD_CONFLICT["quotes"])
    assert GOOD_CONFLICT["shared_situation"] in question
    assert compiled.get_state(CONFIG).next == ("ask_human",)

    done = compiled.invoke(Command(resume="R1 wins: sessions expire after 15 minutes."), config=CONFIG)
    assert done["status"] == "valid"
    assert done["consistency"] == "conflict"  # the flag stays on the record


def test_checked_set_does_not_pause(compiled):
    state = {"requirement": REQS["R3"], "consistency": "checked"}
    assert compiled.invoke(state, config=CONFIG)["status"] == "valid"


# --- per-branch cases ---


def branch(name, stated=True):
    return {"name": name, "condition": f"task is {name}", "expected_stated": stated}


def test_one_case_per_stated_branch_and_questions_for_the_rest(monkeypatch):
    listing = {"branches": [branch("Dispatched"), branch("Arrived"), branch("Open", stated=False)], "reasoning": "r"}
    script(monkeypatch, listing, SPEC, SPEC)
    result = branches.generate_branch_cases("Late Start applies to Dispatched or Arrived tasks.")
    assert result.status == "valid"
    assert [c["branch"] for c in result.cases] == ["Dispatched", "Arrived"]
    assert len(result.questions) == 1 and "Open" in result.questions[0]


def test_branches_are_capped(monkeypatch):
    listing = {"branches": [branch(f"b{i}") for i in range(9)], "reasoning": "r"}
    script(monkeypatch, listing, *[SPEC] * branches.MAX_BRANCHES)
    result = branches.generate_branch_cases("req")
    assert len(result.cases) == branches.MAX_BRANCHES
    assert any("kept the first" in w for w in result.warnings)


def test_a_failed_branch_escalates_instead_of_dropping_silently(monkeypatch):
    listing = {"branches": [branch("a"), branch("b")], "reasoning": "r"}
    script(monkeypatch, listing, SPEC, "bad", "bad")
    result = branches.generate_branch_cases("req")
    assert result.status == "needs_escalation"
    assert [c["branch"] for c in result.cases] == ["a"]
    assert any("'b'" in w for w in result.warnings)


def test_unreadable_branch_listing_escalates(monkeypatch):
    script(monkeypatch, "bad", "bad")
    result = branches.generate_branch_cases("req")
    assert result.status == "needs_escalation" and not result.cases
