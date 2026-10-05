import json

import pytest

from schemas import TestCase, validate_response

GOOD = {
    "title": "Account lockout",
    "description": "Verify lockout after 5 failed logins.",
    "preconditions": ["A registered user exists"],
    "test_steps": ["Enter a wrong password 5 times"],
    "expected_result": "The login form shows an account-locked message.",
    "priority": "high",
}


def check(**overrides):
    return validate_response(json.dumps({**GOOD, **overrides}), TestCase)


def failure_kinds(detail):
    return {kind for kind, _ in detail}


def test_good_spec_is_valid():
    status, tc = check()
    assert status == "valid"
    assert tc.title == "Account lockout"


def test_empty_preconditions_list_is_allowed():
    # testcase_v1.txt says preconditions "can be empty"; requiring one would
    # invite the model to invent it.
    assert check(preconditions=[])[0] == "valid"


@pytest.mark.parametrize("field", ["title", "description", "expected_result"])
@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_blank_required_string_is_invalid(field, blank):
    status, detail = check(**{field: blank})
    assert status == "invalid"
    assert "empty_content" in failure_kinds(detail)
    assert field in str(detail)


def test_empty_test_steps_is_invalid():
    status, detail = check(test_steps=[])
    assert status == "invalid"
    assert "empty_content" in failure_kinds(detail)


@pytest.mark.parametrize("field", ["preconditions", "test_steps"])
def test_blank_list_item_is_invalid(field):
    status, detail = check(**{field: ["real item", "  "]})
    assert status == "invalid"
    assert f"{field}.1" in str(detail)  # points at the offending index


def test_fully_empty_spec_is_invalid():
    # Was returned as valid before the content checks existed.
    status, _ = check(title="", description=" ", preconditions=[], test_steps=[], expected_result="")
    assert status == "invalid"


@pytest.mark.parametrize("priority", ["High", "urgent", "", None, 1])
def test_bad_priority_is_invalid(priority):
    assert check(priority=priority)[0] == "invalid"


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": 123},
        {"test_steps": "one step as a string"},
        {"preconditions": None},
        {"expected_result": ["a", "b"]},
    ],
)
def test_wrong_types_are_invalid(overrides):
    assert check(**overrides)[0] == "invalid"


@pytest.mark.parametrize("field", list(GOOD))
def test_each_missing_field_is_reported(field):
    raw = {k: v for k, v in GOOD.items() if k != field}
    status, detail = validate_response(json.dumps(raw), TestCase)
    assert status == "invalid"
    assert failure_kinds(detail) == {"missing_field"}
    assert field in str(detail)


@pytest.mark.parametrize("raw", ["[]", '"just text"', "null", "42", "true", "[1, 2]"])
def test_valid_json_that_is_not_an_object_does_not_raise(raw):
    # Was an IndexError: validate_response promises it never raises.
    status, detail = validate_response(raw, TestCase)
    assert status == "invalid"
    assert "<root>" in str(detail)


@pytest.mark.parametrize("raw", ["", "not json", '{"title": ', "```json\n{}\n```"])
def test_non_json_is_invalid_json(raw):
    assert validate_response(raw, TestCase)[0] == "invalid_json"


def test_surrounding_whitespace_is_stripped():
    _, tc = check(title="  Account lockout  ")
    assert tc.title == "Account lockout"


def test_unknown_extra_fields_are_dropped_not_rejected():
    # Documented behaviour: extras are ignored, and never reach model_dump().
    status, tc = check(confidence=0.99)
    assert status == "valid"
    assert "confidence" not in tc.model_dump()
