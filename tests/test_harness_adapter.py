import json
from types import SimpleNamespace

import pytest

import graph
from evals import harness_adapter as ha

CLEAN = {
    "has_measurable_condition": True,
    "has_vague_qualitative_language": False,
    "has_ambiguous_scope": False,
    "missing_precondition": False,
    "reasoning": "clear",
}
VAGUE = {**CLEAN, "has_measurable_condition": False, "reasoning": "vague"}
QUESTIONS = {"questions": ["How fast, in seconds?"], "reasoning": "no target"}
SPEC = {
    "title": "Lockout",
    "description": "Verify lockout.",
    "preconditions": [],
    "test_steps": ["Fail login 5 times"],
    "expected_result": "The account is locked.",
    "priority": "high",
}
VAGUE_REQ = "The system should be fast."
CLEAR_REQ = "The system must lock an account after 5 failed logins."


def reply(payload):
    return SimpleNamespace(text=json.dumps(payload), input_tokens=1, output_tokens=7, stop_reason="stop", model_name="fake")


@pytest.fixture
def scripted(monkeypatch):
    """Scripted model: scores by requirement text. Counts scoring calls so a
    test can tell a fresh run from a resumed thread."""
    calls = {"score": 0}

    def fake_json(prompt, *a, **kw):
        if "has_measurable_condition" in prompt:
            calls["score"] += 1
            return reply(VAGUE if "should be fast" in prompt else CLEAN)
        if "matching_test_id" in prompt:
            return reply({"covered": False, "matching_test_id": None, "reasoning": "none"})
        if "clarifying questions" in prompt:
            return reply(QUESTIONS)
        return reply(SPEC)

    monkeypatch.setattr(graph, "call_deepseek_json", fake_json)
    monkeypatch.setattr(graph, "call_deepseek_with_tools", lambda *a, **kw: (SimpleNamespace(tool_calls=None), "stop"))
    monkeypatch.setattr(graph, "search_test_cases", lambda q: [])
    return calls


def write_inputs(tmp_path, labels=None):
    req = tmp_path / "reqs.yaml"
    req.write_text(
        "requirements:\n"
        f"  - id: req_01\n    text: \"{CLEAR_REQ}\"\n"
        f"  - id: req_02\n    text: \"{VAGUE_REQ}\"\n",
        encoding="utf-8",
    )
    lab = tmp_path / "labels.json"
    lab.write_text(json.dumps({"labels": labels or {
        "req_01": {"requirement_ambiguous": False},
        "req_02": {"requirement_ambiguous": True},
    }}), encoding="utf-8")
    return req, lab


def args_for(req, lab, out, runs):
    return SimpleNamespace(requirements=str(req), labels=str(lab), runs=runs, out=str(out))


def test_route_mapping_is_by_caller_behavior():
    assert ha.observed_route("needs_clarification") == "ask"
    assert ha.observed_route("valid") == "emit"
    assert ha.observed_route("already_covered") == "emit"
    assert ha.observed_route("needs_escalation") == "escalate"
    assert ha.observed_route(None) == "escalate"
    assert ha.expected_route({"requirement_ambiguous": True}) == "ask"
    assert ha.expected_route({"requirement_ambiguous": False}) == "emit"


def test_a_missing_label_is_refused_not_defaulted(tmp_path):
    req, lab = write_inputs(tmp_path, labels={"req_01": {"requirement_ambiguous": False}})
    with pytest.raises(SystemExit, match="req_02"):
        ha.load_labels(lab, ha.load_requirements(req))


def test_run_routes_each_requirement_and_writes_only_emitted_specs(scripted, tmp_path):
    req, lab = write_inputs(tmp_path)
    out = tmp_path / "out"
    ha.run_command(args_for(req, lab, out, runs=2))

    routing = {r["case_id"]: r for r in json.loads((out / "routing.json").read_text())["results"]}
    assert routing["req_01__run1"]["observed"] == "emit"
    assert routing["req_02__run2"]["observed"] == "ask"
    assert routing["req_02__run1"]["expected"] == "ask"

    rows = json.loads((out / "agent_rows.json").read_text())["results"]
    assert [r["id"] for r in rows] == ["req_01__run1", "req_01__run2"]  # the paused ones have no spec row
    assert rows[0]["status"] == "valid"
    assert rows[0]["parsed_output"] == SPEC
    assert rows[0]["requirement_text"] == CLEAR_REQ


def test_every_run_gets_its_own_empty_checkpoint_db(scripted, tmp_path, monkeypatch):
    # Same requirement text means the same thread_id. In a shared DB a repeat
    # run inherits the previous run's reask_count and answers, so each run
    # must start from a DB that did not exist before and is gone after.
    import os

    seen = []
    real_start = graph.start_run

    def spy(requirement, *a, **kw):
        seen.append((graph.DB_PATH, os.path.exists(graph.DB_PATH)))
        return real_start(requirement, *a, **kw)

    monkeypatch.setattr(graph, "start_run", spy)
    real_path = graph.DB_PATH
    req, lab = write_inputs(tmp_path)
    ha.run_command(args_for(req, lab, tmp_path / "out", runs=3))

    assert len(seen) == 6
    assert len({path for path, _ in seen}) == 6
    assert not any(existed for _, existed in seen)
    assert not any(os.path.exists(path) for path, _ in seen)
    assert scripted["score"] == 6
    assert graph.DB_PATH == real_path  # the adapter must not leave the module pointed at a deleted temp DB


def test_a_crashing_run_is_recorded_and_the_set_continues(scripted, tmp_path, monkeypatch):
    real = ha.run_agent_once

    def flaky(text):
        if text == VAGUE_REQ:
            raise RuntimeError("boom")
        return real(text)

    monkeypatch.setattr(ha, "run_agent_once", flaky)
    req, lab = write_inputs(tmp_path)
    ha.run_command(args_for(req, lab, tmp_path / "out", runs=1))
    routing = {r["case_id"]: r for r in json.loads((tmp_path / "out" / "routing.json").read_text())["results"]}
    assert routing["req_02__run1"]["status"] == "run_error"
    assert routing["req_02__run1"]["observed"] == "escalate"
    assert routing["req_01__run1"]["observed"] == "emit"


def row(case_id, expected, status):
    return {
        "case_id": case_id,
        "requirement_id": case_id.split("__")[0],
        "run": 1,
        "expected": expected,
        "status": status,
        "observed": ha.observed_route(status),
        "escalation_reason": None,
    }


def test_report_keeps_routing_and_judge_apart_and_counts_each_wrong_way():
    routing = [
        row("a__run1", "emit", "valid"),
        row("a__run2", "emit", "needs_clarification"),   # went the other way
        row("b__run1", "emit", "needs_escalation"),      # escalated
        row("c__run1", "ask", "needs_clarification"),
        row("d__run1", "ask", "valid"),                  # emitted where it should have asked
    ]
    text = ha.build_report(routing, {"a__run1": "good", "d__run1": "bad"})
    assert "expected emit: 1/3 = 33.3% correct (1 went the other way, 1 escalated or errored)" in text
    assert "expected ask: 1/2 = 50.0% correct (1 went the other way, 0 escalated or errored)" in text
    assert "overall: 2/5 = 40.0%" in text
    assert "expected emit: 1/1 = 100.0% good" in text
    assert "expected ask: 0/1 = 0.0% good" in text


def test_report_flags_unstable_requirements_and_missing_judge_scores():
    routing = [row("a__run1", "emit", "valid"), row("a__run2", "emit", "needs_clarification")]
    text = ha.build_report(routing, {})
    assert "route changed between runs: 1 of 1 ['a']" in text
    assert "WARNING: 1 emitted spec(s) have no judge score: ['a__run1']" in text


def test_report_refuses_scores_it_cannot_place():
    with pytest.raises(SystemExit, match="zzz__run1"):
        ha.build_report([row("a__run1", "emit", "valid")], {"zzz__run1": "good"})
