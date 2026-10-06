"""The status contract: every state a caller can observe has an unambiguous
status, and the fields a caller would read for that status are present.

  needs_clarification  paused; clarifying_questions set, test_case None
  valid                spec ready; test_case set
  already_covered      coverage_match set, test_case None
  needs_escalation     test_case None, escalation_reason set
                       (unresolved_ambiguity | spec_generation_failed |
                        scoring_failed | question_generation_failed)
"""

import json
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import graph

REQ = "The system should be fast."

SCORE_CLEAN = {
    "has_measurable_condition": True,
    "has_vague_qualitative_language": False,
    "has_ambiguous_scope": False,
    "missing_precondition": False,
    "reasoning": "clear",
}
SCORE_VAGUE = {**SCORE_CLEAN, "has_measurable_condition": False, "reasoning": "vague"}
QUESTIONS = {"questions": ["How fast, in seconds?"], "reasoning": "no measurable target"}
SPEC = {
    "title": "Response time",
    "description": "Verify response time.",
    "preconditions": [],
    "test_steps": ["Load the page"],
    "expected_result": "The page renders within 3 seconds.",
    "priority": "medium",
}


def reply(payload):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(text=text, input_tokens=1, output_tokens=1, stop_reason="stop", model_name="fake")


def check_contract(state: dict):
    """Assert the shape a caller may rely on for this status."""
    status = state["status"]
    if status == "needs_clarification":
        assert state["clarifying_questions"]
        assert state.get("test_case") is None
    elif status == "valid":
        assert state["test_case"] is not None
    elif status == "already_covered":
        assert state["coverage_match"] is not None
        assert state.get("test_case") is None
    elif status == "needs_escalation":
        assert state.get("test_case") is None
        assert state["escalation_reason"]
    elif status in ("invalid", "invalid_json"):
        assert state.get("test_case") is None
    else:
        pytest.fail(f"unknown status {status!r}")


@pytest.fixture
def app(monkeypatch):
    """Compiled graph with a real checkpointer and a scripted model.
    scores / questions are consumed per call; specs/coverage are fixed."""

    def build(scores, questions=(QUESTIONS,), spec=SPEC):
        score_q, question_q = list(scores), list(questions)

        def fake_json(prompt, *a, **kw):
            if "has_measurable_condition" in prompt:
                return reply(score_q.pop(0))
            if "matching_test_id" in prompt:
                return reply({"covered": False, "matching_test_id": None, "reasoning": "none"})
            if "clarifying questions" in prompt:
                return reply(question_q.pop(0))
            return reply(spec)

        monkeypatch.setattr(graph, "call_deepseek_json", fake_json)
        monkeypatch.setattr(
            graph, "call_deepseek_with_tools", lambda *a, **kw: (SimpleNamespace(tool_calls=None), "stop")
        )
        monkeypatch.setattr(graph, "search_test_cases", lambda q: [])
        return graph.builder.compile(checkpointer=InMemorySaver())

    return build


CONFIG = {"configurable": {"thread_id": "t1"}}


def test_paused_run_is_not_reported_as_valid(app):
    g = app([SCORE_VAGUE])
    result = g.invoke({"requirement": REQ}, config=CONFIG)

    assert "__interrupt__" in result
    assert result["status"] == "needs_clarification"
    assert result.get("test_case") is None  # key may be absent on a pause
    assert g.get_state(CONFIG).next == ("ask_human",)
    check_contract(result)


def test_resume_to_a_clean_spec_ends_valid(app):
    g = app([SCORE_VAGUE, SCORE_CLEAN])
    g.invoke({"requirement": REQ}, config=CONFIG)
    result = g.invoke(Command(resume="Under 3 seconds"), config=CONFIG)

    assert "__interrupt__" not in result
    assert result["status"] == "valid"
    check_contract(result)


def test_pause_status_does_not_leak_into_a_terminal_result(app):
    # needs_clarification must be replaced by whatever ends the run.
    g = app([SCORE_VAGUE, SCORE_CLEAN])
    g.invoke({"requirement": REQ}, config=CONFIG)
    result = g.invoke(Command(resume="Under 3 seconds"), config=CONFIG)
    assert result["status"] != "needs_clarification"


def test_reask_exhaustion_escalates(app):
    # vague, answer, vague, answer, vague -> guard exhausted
    g = app([SCORE_VAGUE] * 3, questions=[QUESTIONS] * 2)
    g.invoke({"requirement": REQ}, config=CONFIG)
    g.invoke(Command(resume="faster"), config=CONFIG)
    result = g.invoke(Command(resume="much faster"), config=CONFIG)

    assert result["status"] == "needs_escalation"
    assert result["escalation_reason"] == "unresolved_ambiguity"
    check_contract(result)


def test_scorer_failure_on_the_rescore_after_resume_escalates_and_keeps_the_answer(app):
    # First score is fine and pauses; the re-score after the human answers
    # never validates. Must escalate, not ask a second round, not emit a spec.
    g = app([SCORE_VAGUE] + ["not json"] * graph.MAX_CALL_ATTEMPTS)
    g.invoke({"requirement": REQ}, config=CONFIG)
    result = g.invoke(Command(resume="Under 3 seconds"), config=CONFIG)

    assert "__interrupt__" not in result
    assert result["status"] == "needs_escalation"
    assert result["escalation_reason"] == "scoring_failed"
    assert result["human_answers"] == ["Under 3 seconds"]  # the human's work isn't lost
    assert result["reask_count"] == 1  # the round that was already spent, no new one
    check_contract(result)


@pytest.mark.parametrize("bad_questions", [{"questions": [], "reasoning": "x"}, "not json", "[]"])
def test_failed_question_generation_escalates_without_pausing(app, bad_questions):
    g = app([SCORE_VAGUE], questions=[bad_questions] * graph.MAX_CALL_ATTEMPTS)
    result = g.invoke({"requirement": REQ}, config=CONFIG)

    assert "__interrupt__" not in result  # nothing real to show a human
    assert result["status"] == "needs_escalation"
    assert result["escalation_reason"] == "question_generation_failed"
    assert g.get_state(CONFIG).next == ()
    check_contract(result)
