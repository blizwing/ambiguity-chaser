"""
Runs the agent over an eval-harness requirement set and scores it with the
harness's judge. Run from the repo root:

    python -m evals.harness_adapter run --requirements <yaml> --labels <json> [--runs 3] [--out private/harness_run]
    python -m evals.harness_adapter report --out private/harness_run --scores <Day24 score json>

The harness is not imported (it has its own `schemas.py`, which would collide
with this repo's). The two sides meet only through JSON files:

  run     -> agent_rows.json   emitted specs only, in the harness's row shape;
                               score it from the eval-harness folder with
                               `python Day24_scorer.py --mode judge --results-file <agent_rows.json> --output-file <scores.json>`
          -> routing.json      every run: expected route, observed route
  report  <- routing.json + the scorer's output

The harness assumes every requirement should yield a test case. This agent is
built to ask instead on an ambiguous one, so "no spec" cannot count as a
failure. Expected route comes from the harness's own labels:
`requirement_ambiguous: true` means ask, otherwise emit. Three numbers are
reported and never merged: routing accuracy, judge pass rate on emitted specs,
and both split by expected group.

Each run starts from a fresh throwaway checkpoint DB: thread_id is a hash of
the requirement text, so in a shared DB a repeat run re-executes but inherits
the previous run's checkpointed state (checked: a second run started with
`reask_count` 2 and the earlier answers). A paused run is never resumed;
stopping at the first pause is what "asked" means here. Lone runs, so the
set-level consistency check is not exercised.

Observed route from the final `status`:
  needs_clarification              -> ask
  valid, already_covered           -> emit   (cleared the testability gate)
  needs_escalation, anything else  -> escalate (right for neither group)
"""

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

DEFAULT_OUT = Path("private/harness_run")
DEFAULT_RUNS = 3
ROUTE_OF_STATUS = {"needs_clarification": "ask", "valid": "emit", "already_covered": "emit"}


def expected_route(label: dict) -> str:
    return "ask" if label["requirement_ambiguous"] else "emit"


def observed_route(status: str | None) -> str:
    return ROUTE_OF_STATUS.get(status, "escalate")


def load_requirements(path: Path) -> list[dict]:
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    reqs = parsed["requirements"]
    ids = [r["id"] for r in reqs]
    if len(set(ids)) != len(ids):
        raise SystemExit(f"duplicate requirement ids in {path}")
    return reqs


def load_labels(path: Path, reqs: list[dict]) -> dict[str, dict]:
    labels = json.loads(path.read_text(encoding="utf-8"))["labels"]
    missing = [r["id"] for r in reqs if r["id"] not in labels]
    if missing:
        # No default: a guessed expectation would make routing accuracy meaningless.
        raise SystemExit(f"no label for requirement(s) {missing}; refusing to guess an expected route")
    return labels


def spec_row(case_id: str, requirement_text: str, state: dict) -> dict:
    """One harness row (the shape Day23_runner.serialize_case writes). Only
    the fields the judge path reads are meaningful; token fields are absent
    because the assertions mode, which needs them, is not used here."""
    return {
        "id": case_id,
        "requirement_text": requirement_text,
        "status": "valid",
        "attempts": 1,
        "parsed_output": state["test_case"],
        "raw_response_text": json.dumps(state["test_case"], ensure_ascii=False),
        "validation_detail": None,
        "error_message": None,
    }


def run_agent_once(requirement: str) -> tuple[dict, int]:
    """Returns (final state, output tokens used). Fresh DB per call."""
    import graph  # lazy: importing it needs an API key, `report` does not

    tokens = 0
    real_call = graph.call_deepseek_json

    def counting_call(*args, **kwargs):
        nonlocal tokens
        result = real_call(*args, **kwargs)
        tokens += result.output_tokens
        return result

    real_db_path = graph.DB_PATH
    graph.call_deepseek_json = counting_call
    try:
        with tempfile.TemporaryDirectory() as tmp:
            graph.DB_PATH = str(Path(tmp) / "graph_state.db")
            state = graph.start_run(requirement)
    finally:
        graph.call_deepseek_json = real_call
        graph.DB_PATH = real_db_path
    return state, tokens


def run_command(args) -> None:
    reqs = load_requirements(Path(args.requirements))
    labels = load_labels(Path(args.labels), reqs)
    total = len(reqs) * args.runs
    print(f"{len(reqs)} requirements x {args.runs} runs = {total} agent runs (real API calls)")

    rows, routing, tokens_total = [], [], 0
    for req in reqs:
        text = req["text"].strip()
        for n in range(1, args.runs + 1):
            case_id = f"{req['id']}__run{n}"
            try:
                state, tokens = run_agent_once(text)
                status, reason = state.get("status"), state.get("escalation_reason")
            except Exception as e:  # one bad run must not kill the set
                state, tokens, status, reason = {}, 0, "run_error", f"{type(e).__name__}: {e}"
            tokens_total += tokens
            routing.append({
                "case_id": case_id,
                "requirement_id": req["id"],
                "run": n,
                "expected": expected_route(labels[req["id"]]),
                "status": status,
                "observed": observed_route(status),
                "escalation_reason": reason,
            })
            if status == "valid" and state.get("test_case") is not None:
                rows.append(spec_row(case_id, text, state))
            print(f"  {case_id}: {status}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    (out / "agent_rows.json").write_text(json.dumps({
        "generated_at": stamp,
        "source_requirements_file": Path(args.requirements).name,
        "count": len(rows),
        "results": rows,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "routing.json").write_text(json.dumps({
        "generated_at": stamp,
        "runs_per_requirement": args.runs,
        "output_tokens_total": tokens_total,
        "results": routing,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(rows)} emitted specs -> {out / 'agent_rows.json'}  (score with Day24_scorer.py --mode judge)")
    print(f"routing -> {out / 'routing.json'}; output tokens used: {tokens_total}")


def _rate(num: int, den: int) -> str:
    return "n/a (0 cases)" if den == 0 else f"{num}/{den} = {100 * num / den:.1f}%"


def build_report(routing: list[dict], verdicts: dict[str, str]) -> str:
    """verdicts maps case_id -> judge verdict for emitted specs. Pure function
    so it can be tested without files."""
    lines = ["Routing (did it ask or emit as expected?)"]
    for group in ("ask", "emit"):
        rows = [r for r in routing if r["expected"] == group]
        right = sum(r["observed"] == group for r in rows)
        wrong_way = sum(r["observed"] in ("ask", "emit") and r["observed"] != group for r in rows)
        escalated = sum(r["observed"] == "escalate" for r in rows)
        lines.append(
            f"  expected {group}: {_rate(right, len(rows))} correct"
            f" ({wrong_way} went the other way, {escalated} escalated or errored)"
        )
    lines.append(f"  overall: {_rate(sum(r['observed'] == r['expected'] for r in routing), len(routing))}")

    flipped = {}
    for r in routing:
        flipped.setdefault(r["requirement_id"], set()).add(r["observed"])
    unstable = sorted(rid for rid, seen in flipped.items() if len(seen) > 1)
    lines.append(f"  requirements whose route changed between runs: {len(unstable)} of {len(flipped)} {unstable}")

    lines.append("")
    lines.append("Judge on emitted specs (strict: only 'good' passes; never merged with routing)")
    expected_of = {r["case_id"]: r["expected"] for r in routing}
    unscored = sorted(c for c in verdicts if c not in expected_of)
    if unscored:
        raise SystemExit(f"scores for cases not in routing.json: {unscored}")
    for group in ("emit", "ask"):
        ids = [c for c in verdicts if expected_of[c] == group]
        good = sum(verdicts[c] == "good" for c in ids)
        note = "" if group == "emit" else "  (specs emitted where the agent should have asked)"
        lines.append(f"  expected {group}: {_rate(good, len(ids))} good{note}")
    emitted_missing = sorted(
        r["case_id"] for r in routing if r["status"] == "valid" and r["case_id"] not in verdicts
    )
    if emitted_missing:
        lines.append(f"  WARNING: {len(emitted_missing)} emitted spec(s) have no judge score: {emitted_missing}")
    return "\n".join(lines)


def report_command(args) -> None:
    out = Path(args.out)
    routing = json.loads((out / "routing.json").read_text(encoding="utf-8"))["results"]
    scores = json.loads(Path(args.scores).read_text(encoding="utf-8"))["results"]
    verdicts = {s["case_id"]: s["judge_result"]["verdict"] for s in scores}
    print(build_report(routing, verdicts))


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the agent over a requirement set")
    run.add_argument("--requirements", required=True, help="eval-harness requirements YAML")
    run.add_argument("--labels", required=True, help="eval-harness labels JSON (needs requirement_ambiguous)")
    run.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    run.add_argument("--out", default=str(DEFAULT_OUT))
    run.set_defaults(func=run_command)

    report = sub.add_parser("report", help="combine routing with the harness judge scores")
    report.add_argument("--out", default=str(DEFAULT_OUT))
    report.add_argument("--scores", required=True, help="Day24_scorer.py output JSON")
    report.set_defaults(func=report_command)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
