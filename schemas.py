"""
Pydantic models for this repo, ported from eval-harness's schemas.py /
Day5_validate.py. Only TestCase and validate_response are ported today —
the rest of eval-harness's model zoo (Requirement, JudgeScore, etc.) isn't
used by this graph yet and isn't ported until something here actually
needs it.
"""

import json
from typing import Literal

from pydantic import BaseModel, ValidationError


class TestCase(BaseModel):
    title: str
    description: str
    preconditions: list[str]
    test_steps: list[str]
    expected_result: str
    priority: Literal["low", "medium", "high"]


class TestabilityScore(BaseModel):
    """Facts the model reports about a requirement, not a score — Python
    derives the actual score from these booleans (compute_testability_score),
    never trusting the model to do its own arithmetic."""
    has_measurable_condition: bool
    has_vague_qualitative_language: bool
    has_ambiguous_scope: bool
    missing_precondition: bool
    reasoning: str


class ClarifyingQuestions(BaseModel):
    questions: list[str]
    reasoning: str


# 86, not 85: soft deductions are -15 each, so one soft failure scores
# exactly 85. Intent is zero soft failures tolerated, and route_by_testability
# checks score >= TESTABILITY_THRESHOLD, so the threshold has to clear 85,
# not equal it.
TESTABILITY_THRESHOLD = 86


def compute_testability_score(ts: TestabilityScore) -> int:
    """Deduction scoring, Pratham's call: has_measurable_condition is a hard
    gate — fail it and the score is 0 regardless of the other criteria,
    since there's nothing to test without at least one verifiable condition.
    Each remaining (soft) criterion that's present costs 15 points off 100."""
    if not ts.has_measurable_condition:
        return 0

    score = 100
    if ts.has_vague_qualitative_language:
        score -= 15
    if ts.has_ambiguous_scope:
        score -= 15
    if ts.missing_precondition:
        score -= 15
    return score


def validate_response(raw_text: str, model: type[BaseModel]):
    """Parses raw_text as JSON and validates it against model. Returns
    ("valid", <model instance>), ("invalid_json", [<error>]), or
    ("invalid", [<failure descriptions>]) — never raises, since a model's
    malformed output is expected input here, not a bug in this code."""
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return ("invalid_json", [str(e)])

    try:
        result = model.model_validate(parsed)
    except ValidationError as e:
        errors = e.errors()
        missing = [err["loc"][0] for err in errors if err["type"] == "missing"]
        wrong_type = [
            (err["loc"][0], err["type"], err["msg"])
            for err in errors
            if err["type"] != "missing"
        ]

        failures = []
        if missing:
            failures.append(("missing_field", f"Missing required field(s): {missing}"))
        if wrong_type:
            failures.append(("wrong_type", wrong_type))
        return ("invalid", failures)

    return ("valid", result)
