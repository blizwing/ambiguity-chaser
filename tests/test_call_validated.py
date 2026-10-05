"""The shared call-validate-repair mechanic, and how the scorer and question
generator use it. Model calls are scripted; token budgets are recorded."""

import json
from types import SimpleNamespace

import pytest

import graph
from graph import GraphState, MAX_CALL_ATTEMPTS, MAX_TOKENS, MAX_TOKENS_CAP
from schemas import ClarifyingQuestions, TestabilityScore

SCORE_CLEAN = {
    "has_measurable_condition": True,
    "has_vague_qualitative_language": False,
    "has_ambiguous_scope": False,
    "missing_precondition": False,
    "reasoning": "clear",
}
QUESTIONS = {"questions": ["How fast?"], "reasoning": "vague"}
TRUNCATED = ("", "length")  # what a reasoning model returns when reasoning eats the budget


def reply(item):
    text, stop = item if isinstance(item, tuple) else (item if isinstance(item, str) else json.dumps(item), "stop")
    return SimpleNamespace(text=text, input_tokens=1, output_tokens=1, stop_reason=stop, model_name="fake")


@pytest.fixture
def scripted(monkeypatch):
    calls: list[dict] = []

    def install(*items):
        queue = list(items)

        def fake(prompt, *a, **kw):
            calls.append({"prompt": prompt, "max_tokens": kw.get("max_tokens")})
            assert queue, "model called more times than scripted"
            return reply(queue.pop(0))

        monkeypatch.setattr(graph, "call_deepseek_json", fake)
        return calls

    return install


# --- the helper -------------------------------------------------------------

def test_clean_first_try(scripted):
    calls = scripted(SCORE_CLEAN)
    detail, errors, attempts = graph._call_validated("p", TestabilityScore)
    assert detail is not None and errors == [] and attempts == 1
    assert calls[0]["max_tokens"] == MAX_TOKENS


def test_truncation_retries_with_bigger_budget_and_same_prompt(scripted):
    calls = scripted(TRUNCATED, SCORE_CLEAN)
    detail, errors, attempts = graph._call_validated("p", TestabilityScore)

    assert detail is not None and attempts == 2
    assert calls[1]["max_tokens"] == MAX_TOKENS * 2
    assert calls[1]["prompt"] == "p"  # no "rejected" feedback: it can't fix a spent budget
    assert "truncated" in errors[0]


def test_invalid_output_retries_with_feedback_and_same_budget(scripted):
    calls = scripted({"has_measurable_condition": "maybe"}, SCORE_CLEAN)
    detail, errors, _ = graph._call_validated("p", TestabilityScore)

    assert detail is not None
    assert "rejected" in calls[1]["prompt"]
    assert calls[1]["max_tokens"] == MAX_TOKENS
    assert errors and "truncated" not in errors[0]


def test_budget_is_capped(monkeypatch, scripted):
    monkeypatch.setattr(graph, "MAX_CALL_ATTEMPTS", 6)
    calls = scripted(*[TRUNCATED] * 6)
    graph._call_validated("p", TestabilityScore)
    assert max(c["max_tokens"] for c in calls) == MAX_TOKENS_CAP


def test_gives_up_after_bounded_attempts(scripted):
    calls = scripted(*[TRUNCATED] * 10)
    detail, errors, attempts = graph._call_validated("p", TestabilityScore)
    assert detail is None
    assert len(calls) == attempts == MAX_CALL_ATTEMPTS
    assert len(errors) == MAX_CALL_ATTEMPTS


def test_complete_valid_json_is_kept_even_if_finish_reason_is_length(scripted):
    # Output that happens to end exactly at the limit but validates is fine.
    scripted((json.dumps(SCORE_CLEAN), "length"))
    detail, errors, attempts = graph._call_validated("p", TestabilityScore)
    assert detail is not None and attempts == 1 and errors == []


def test_check_rejects_schema_valid_but_unusable_result(scripted):
    scripted({"questions": [], "reasoning": "x"}, QUESTIONS)
    detail, errors, attempts = graph._call_validated(
        "p", ClarifyingQuestions, check=lambda d: None if d.questions else "questions list is empty"
    )
    assert detail.questions == ["How fast?"] and attempts == 2
    assert errors == ["questions list is empty"]


# --- scorer -----------------------------------------------------------------

def score(state=None):
    return graph.score_testability(state or GraphState(requirement="x"))


def test_scorer_recovers_from_a_truncated_reply(scripted):
    scripted(TRUNCATED, SCORE_CLEAN)
    out = score()
    assert out["testability_score"] == 100
    assert out["call_attempts"] == 2 and out["call_errors"]


def test_scorer_failure_is_not_a_score_of_zero(scripted):
    scripted(*[TRUNCATED] * 2)
    out = score()
    assert out["testability_score"] is None  # not 0: 0 means "scored, untestable"
    assert out["status"] == "needs_escalation"
    assert out["escalation_reason"] == "scoring_failed"


def test_scorer_failure_routes_to_end_not_to_questions():
    state = GraphState(requirement="x", escalation_reason="scoring_failed", testability_score=None)
    assert graph.route_by_testability(state) == "end"


def test_scorer_failure_does_not_spend_a_human_reask_round(scripted):
    scripted(*[TRUNCATED] * 2)
    result = graph.builder.compile().invoke({"requirement": "x"})
    assert result["status"] == "needs_escalation"
    assert result["escalation_reason"] == "scoring_failed"
    assert result.get("reask_count", 0) == 0
    assert not result.get("clarifying_questions")


# --- question generator -------------------------------------------------------

def questions():
    detail = {**SCORE_CLEAN, "has_measurable_condition": False}
    return graph.generate_questions(GraphState(requirement="x", testability_detail=detail))


def test_questions_recover_from_an_empty_list(scripted):
    scripted({"questions": [], "reasoning": "x"}, QUESTIONS)
    out = questions()
    assert out["status"] == "needs_clarification"
    assert out["clarifying_questions"] == ["How fast?"]


def test_questions_recover_from_a_truncated_reply(scripted):
    scripted(TRUNCATED, QUESTIONS)
    assert questions()["status"] == "needs_clarification"


def test_question_failure_clears_stale_questions_and_escalates(scripted):
    scripted(*[TRUNCATED] * 2)
    out = questions()
    assert out["status"] == "needs_escalation"
    assert out["escalation_reason"] == "question_generation_failed"
    assert out["clarifying_questions"] is None
