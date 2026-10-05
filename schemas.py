"""
Pydantic models for this repo, ported from eval-harness's schemas.py /
Day5_validate.py. Only TestCase and validate_response are ported today —
the rest of eval-harness's model zoo (Requirement, JudgeScore, etc.) isn't
used by this graph yet and isn't ported until something here actually
needs it.
"""

import json
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, ValidationError


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value.strip()


# A schema-valid-but-empty string/list is not a usable spec field (same
# discipline as the questions: [] check in generate_questions).
NonBlankStr = Annotated[str, AfterValidator(_non_blank)]


class TestCase(BaseModel):
    title: NonBlankStr
    description: NonBlankStr
    # Items must be non-blank but the list itself may be empty, matching
    # testcase_v1.txt ("can be empty"). Requiring >=1 would push the model
    # to invent a precondition the requirement never stated.
    preconditions: list[NonBlankStr]
    test_steps: Annotated[list[NonBlankStr], Field(min_length=1)]
    expected_result: NonBlankStr
    priority: Literal["low", "medium", "high"]


EXPECTED_RESULT_MAX_WORDS = 25  # the testcase prompt's own rule


def spec_style_problem(tc: "TestCase") -> str | None:
    """Soft rule the prompt states but that doesn't make a spec wrong: a
    long expected_result is worth one repair attempt, never an escalation."""
    words = len(tc.expected_result.split())
    if words > EXPECTED_RESULT_MAX_WORDS:
        return (
            f"expected_result is {words} words; it must be {EXPECTED_RESULT_MAX_WORDS} or fewer. "
            "Keep it a single pass/fail condition and put any ambiguity note in description"
        )
    return None


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

class SearchArgs(BaseModel):
    query: str


class CoverageVerdict(BaseModel):
    covered:bool
    matching_test_id: str | None
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

        def where(err) -> str:
            # loc is () when the JSON isn't an object at all ([], "x", null)
            return ".".join(str(part) for part in err["loc"]) or "<root>"

        # Present-but-unusable values (blank string, empty required list)
        # get their own bucket: the repair prompt should say "empty", not
        # "wrong type".
        empty_types = {"value_error", "too_short"}
        missing = [where(err) for err in errors if err["type"] == "missing"]
        empty = [(where(err), err["msg"]) for err in errors if err["type"] in empty_types]
        wrong_type = [
            (where(err), err["type"], err["msg"])
            for err in errors
            if err["type"] != "missing" and err["type"] not in empty_types
        ]

        failures = []
        if missing:
            failures.append(("missing_field", f"Missing required field(s): {missing}"))
        if empty:
            failures.append(("empty_content", empty))
        if wrong_type:
            failures.append(("wrong_type", wrong_type))
        return ("invalid", failures)

    return ("valid", result)
