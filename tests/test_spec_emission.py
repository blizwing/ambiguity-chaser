"""Spec emission (Week 13): a spec reaches the caller only if it passes
validation; a bad one gets one repair attempt, then escalates."""

import json
from types import SimpleNamespace

import pytest

import graph
from graph import GraphState, MAX_SPEC_ATTEMPTS

GOOD = {
    "title": "Account lockout",
    "description": "Verify lockout after 5 failed logins.",
    "preconditions": [],
    "test_steps": ["Enter a wrong password 5 times"],
    "expected_result": "The login form shows an account-locked message.",
    "priority": "high",
}
EMPTY_SPEC = {**GOOD, "title": "", "test_steps": []}
SCORE_CLEAN = {
    "has_measurable_condition": True,
    "has_vague_qualitative_language": False,
    "has_ambiguous_scope": False,
    "missing_precondition": False,
    "reasoning": "clear",
}


def reply(payload) -> SimpleNamespace:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(text=text, input_tokens=1, output_tokens=1, stop_reason="stop", model_name="fake")


@pytest.fixture
def scripted(monkeypatch):
    """Feed generate_test_case a fixed sequence of model replies; record prompts."""
    prompts: list[str] = []

    def install(*replies):
        queue = list(replies)

        def fake(prompt, *a, **kw):
            prompts.append(prompt)
            assert queue, "model called more times than the test scripted"
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return reply(item)

        monkeypatch.setattr(graph, "call_deepseek_json", fake)
        return prompts

    return install


def run(requirement="Lock the account after 5 failed logins"):
    return graph.generate_test_case(GraphState(requirement=requirement))


def test_valid_first_try_makes_one_call(scripted):
    prompts = scripted(GOOD)
    out = run()
    assert out["status"] == "valid"
    assert out["test_case"]["title"] == "Account lockout"
    assert out["spec_attempts"] == 1
    assert len(prompts) == 1


def test_invalid_then_valid_repairs_with_feedback(scripted):
    prompts = scripted(EMPTY_SPEC, GOOD)
    out = run()
    assert out["status"] == "valid"
    assert out["spec_attempts"] == 2
    assert "rejected" in prompts[1] and "title" in prompts[1] and "test_steps" in prompts[1]
    assert "rejected" not in prompts[0]


def test_invalid_json_then_valid(scripted):
    scripted("I am sorry, here is your test case: ...", GOOD)
    assert run()["status"] == "valid"


def test_non_object_json_then_valid(scripted):
    scripted("[]", GOOD)  # used to raise IndexError inside validate_response
    assert run()["status"] == "valid"


def test_invalid_twice_escalates_and_emits_no_spec(scripted):
    prompts = scripted(EMPTY_SPEC, EMPTY_SPEC)
    out = run()
    assert out["status"] == "needs_escalation"
    assert out["escalation_reason"] == "spec_generation_failed"
    assert out["test_case"] is None
    assert out["spec_attempts"] == MAX_SPEC_ATTEMPTS
    assert out["spec_errors"]
    assert len(prompts) == MAX_SPEC_ATTEMPTS  # bounded: never loops


def test_repaired_spec_keeps_first_attempt_errors_for_diagnosis(scripted):
    scripted(EMPTY_SPEC, GOOD)
    out = run()
    assert out["status"] == "valid"
    assert out["spec_errors"] and "title" in out["spec_errors"][0]


def test_clean_first_try_has_no_errors(scripted):
    scripted(GOOD)
    assert run()["spec_errors"] is None


def test_api_exception_still_propagates(scripted):
    # Documented design: bad *output* is handled, an API failure is not
    # swallowed into a spec-shaped result.
    scripted(RuntimeError("503 from provider"))
    with pytest.raises(RuntimeError):
        run()


def test_mark_unresolved_records_its_reason():
    out = graph.mark_unresolved(GraphState(requirement="x"))
    assert out == {"status": "needs_escalation", "escalation_reason": "unresolved_ambiguity"}


# --- end to end through the compiled graph (no checkpointer needed: no pause) ---

TERMINAL_INVARIANTS = {
    "valid": lambda r: r["test_case"] is not None,
    "already_covered": lambda r: r["coverage_match"] is not None and r["test_case"] is None,
    "needs_escalation": lambda r: r["test_case"] is None and r["escalation_reason"] is not None,
}


@pytest.fixture
def full_graph(monkeypatch):
    def install(spec_replies):
        queue = list(spec_replies)

        def fake_json(prompt, *a, **kw):
            if "has_measurable_condition" in prompt:
                return reply(SCORE_CLEAN)
            if "matching_test_id" in prompt:
                return reply({"covered": False, "matching_test_id": None, "reasoning": "none"})
            return reply(queue.pop(0))

        monkeypatch.setattr(graph, "call_deepseek_json", fake_json)
        monkeypatch.setattr(
            graph, "call_deepseek_with_tools", lambda *a, **kw: (SimpleNamespace(tool_calls=None), "stop")
        )
        monkeypatch.setattr(graph, "search_test_cases", lambda q: [])
        return graph.builder.compile()

    return install


def test_end_to_end_good_spec(full_graph):
    result = full_graph([GOOD]).invoke({"requirement": "Lock the account after 5 failed logins"})
    assert result["status"] == "valid"
    assert TERMINAL_INVARIANTS["valid"](result)


def test_end_to_end_unrecoverable_spec_escalates(full_graph):
    result = full_graph([EMPTY_SPEC, EMPTY_SPEC]).invoke({"requirement": "Lock the account after 5 failed logins"})
    assert result["status"] == "needs_escalation"
    assert TERMINAL_INVARIANTS["needs_escalation"](result)
