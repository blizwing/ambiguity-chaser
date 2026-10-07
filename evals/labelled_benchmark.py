"""
Scores the set-level consistency check against a labelled benchmark of
requirement sets. Run from the repo root:

    python -m evals.labelled_benchmark [runs] [whole|examples]

`whole` is the one-call set check; `examples` is one example-versus-rules call
per requirement that has an example (default `examples`).

The benchmark file is not part of this repo. Point the AMBIGUITY_BENCHMARK
environment variable at a JSON file shaped like:

    [{"id": "T1",
      "requirements": {"R1": "...", "R2": "..."},
      "issues": [{"id": "I1", "req_ids": ["R1", "R2"]}]}]

Only ids and counts are printed, never requirement text. Each set is run
`runs` times because temperature=0 is not fully deterministic; results are
rates, not one result.

  caught         a labelled issue matched by a grounded conflict (see score_run)
  missed         a labelled issue no grounded conflict matched
  falsely raised a grounded conflict that overlaps no labelled issue
  not_checked    runs where the check never produced a validated report
"""

import json
import os
import sys
from pathlib import Path

import consistency


def benchmark_path() -> Path:
    value = os.environ.get("AMBIGUITY_BENCHMARK")
    if not value:
        raise SystemExit("Set AMBIGUITY_BENCHMARK to the path of the benchmark JSON file.")
    return Path(value)


def load_benchmark() -> list[dict]:
    path = benchmark_path()
    with open(path, encoding="utf-8-sig") as f:  # tolerate a BOM from Windows editors
        sets = json.load(f)
    for s in sets:
        known = set(s["requirements"])
        for issue in s["issues"]:
            unknown = set(issue["req_ids"]) - known
            if unknown:
                raise ValueError(f"{s['id']}/{issue['id']} names unknown requirement ids {sorted(unknown)}")
    return sets


CHECKS = {"whole": consistency.check_consistency, "examples": consistency.check_examples}


def score_run(bench_set: dict, check) -> dict:
    """An issue is caught if a grounded conflict names at least 2 of its
    requirements and none outside it (labelled issues span 2-5 requirements, and a
    conflict is reported as a set of ids). A conflict is falsely raised if it
    shares fewer than 2 requirements with every labelled issue. Single-
    requirement issues are not cross-requirement conflicts, so they are out of
    scope for this check and reported separately."""
    result = check(bench_set["requirements"])
    found = [set(c["req_ids"]) for c in result.conflicts]
    issues = {i["id"]: set(i["req_ids"]) for i in bench_set["issues"]}
    in_scope = {iid: ids for iid, ids in issues.items() if len(ids) >= 2}
    caught = {
        iid for iid, ids in in_scope.items()
        if any(len(c & ids) >= 2 and c <= ids for c in found)
    }
    false_raised = [c for c in found if not any(len(c & ids) >= 2 for ids in in_scope.values())]
    return {
        "status": result.status,
        "in_scope": set(in_scope),
        "out_of_scope": set(issues) - set(in_scope),
        "caught": caught,
        "false_raised": len(false_raised),
    }


def main(runs: int, mode: str) -> None:
    check = CHECKS[mode]
    sets = load_benchmark()
    total_issues = caught_total = false_total = not_checked_total = run_total = 0
    for s in sets:
        outcomes = [score_run(s, check) for _ in range(runs)]
        scope = sorted(outcomes[0]["in_scope"])
        out_scope = sorted(outcomes[0]["out_of_scope"])
        caught = sum(len(o["caught"]) for o in outcomes)
        false_raised = sum(o["false_raised"] for o in outcomes)
        not_checked = sum(o["status"] == "not_checked" for o in outcomes)
        per_issue = {iid: sum(iid in o["caught"] for o in outcomes) for iid in scope}
        print(
            f"{s['id']:12} in-scope issues: {len(scope)}   caught: {caught}/{len(scope) * runs}   "
            f"falsely raised: {false_raised}   not_checked: {not_checked}/{runs}"
        )
        print(f"{'':12} per issue: " + ", ".join(f"{k} {v}/{runs}" for k, v in per_issue.items()))
        if out_scope:
            print(f"{'':12} out of scope (single requirement): {', '.join(out_scope)}")
        total_issues += len(scope) * runs
        caught_total += caught
        false_total += false_raised
        not_checked_total += not_checked
        run_total += runs

    print(f"\ncaught:         {caught_total}/{total_issues}")
    print(f"missed:         {total_issues - caught_total}/{total_issues}")
    print(f"falsely raised: {false_total} across {run_total} runs")
    print(f"not_checked:    {not_checked_total}/{run_total}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5, sys.argv[2] if len(sys.argv) > 2 else "examples")
