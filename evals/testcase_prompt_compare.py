"""
Does testcase_v3's example-conflict rule change what the generator says?
Run from the repo root:  python -m evals.testcase_prompt_compare [runs]

Runs testcase_v2 and testcase_v3 over invented requirements whose example
contradicts the stated rule, plus a control with a consistent example, and
counts how often the description flags the conflict. Keyword match is a
rough proxy: read a few descriptions yourself before trusting the rates.
"""

import re
import sys

from graph import _call_validated
from schemas import TestCase

CASES = [
    # (id, requirement, example_conflicts)
    (
        "example_contradicts_rule",
        "A guest session expires after 15 minutes of inactivity. Example: a guest idles from 10:00 and "
        "is still signed in at 10:40 with items in the cart; this is correct.",
        True,
    ),
    (
        "example_contradicts_limit",
        "A guest may place at most 3 orders per email in 30 days. Example: a guest places a fourth "
        "order on day 20 and it is accepted.",
        True,
    ),
    (
        "example_consistent",
        "A guest session expires after 15 minutes of inactivity. Example: a guest idles from 10:00 and "
        "is signed out at 10:15.",
        False,
    ),
]
FLAG = re.compile(r"conflict|contradict|inconsisten|does not match|doesn't match", re.I)
PROMPTS = {v: open(f"prompts/testcase_{v}.txt", encoding="utf-8").read() for v in ("v2", "v3")}


def main(runs: int) -> None:
    for version, prompt in PROMPTS.items():
        for case_id, requirement, should_flag in CASES:
            flagged = 0
            for _ in range(runs):
                detail, _, _, _ = _call_validated(prompt.format(requirement=requirement), TestCase)
                flagged += bool(detail and FLAG.search(detail.description))
            print(f"{version} {case_id:28} flags conflict: {flagged}/{runs}   (should flag: {should_flag})")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
