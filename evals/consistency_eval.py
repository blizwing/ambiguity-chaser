"""
Measures the set-level consistency check instead of trusting it (Week 15).
Run from the repo root:  python -m evals.consistency_eval [runs]

Each case is run `runs` times (default 5; temperature=0 is not fully
deterministic, so this reports rates, never one exact result). Cases come
from evals/consistency_cases.json: invented requirements only.

  catch rate         planted cases where a grounded conflict names exactly
                     the expected requirement pair
  false-alarm rate   near-miss / clean cases where any grounded conflict
                     was reported (each one would pause a real run)
  dropped claims     conflicts the model claimed that failed the quote check
"""

import json
import sys

import consistency

with open("evals/consistency_cases.json", encoding="utf-8") as f:
    CASES = json.load(f)


def run_case(case: dict) -> dict:
    result = consistency.check_consistency(case["requirements"])
    found = [sorted(c["req_ids"]) for c in result.conflicts]
    expected = sorted(case["expected_conflict"]) if case["expected_conflict"] else None
    accepted = [expected] + [sorted(a) for a in case.get("also_accept", [])] if expected else []
    return {
        "status": result.status,
        "caught": any(a in found for a in accepted) if expected else None,
        "alarm": bool(found) if expected is None else None,
        "dropped": sum("dropped" in w for w in result.warnings),
    }


def main(runs: int) -> None:
    tallies: dict[str, list[dict]] = {}
    for case in CASES:
        outcomes = [run_case(case) for _ in range(runs)]
        tallies[case["id"]] = outcomes
        key = "caught" if case["kind"] == "planted" else "alarm"
        hits = sum(o[key] for o in outcomes)
        not_checked = sum(o["status"] == "not_checked" for o in outcomes)
        print(f"{case['id']:34} {key}: {hits}/{runs}   not_checked: {not_checked}   dropped: {sum(o['dropped'] for o in outcomes)}")

    def rate(kinds, key):
        rows = [o for c in CASES if c["kind"] in kinds for o in tallies[c["id"]]]
        return sum(o[key] for o in rows), len(rows)

    caught, n = rate({"planted"}, "caught")
    print(f"\ncatch rate (planted):          {caught}/{n}")
    for kind in ("near_miss", "clean"):
        alarms, n = rate({kind}, "alarm")
        print(f"false-alarm rate ({kind:9}):   {alarms}/{n}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
