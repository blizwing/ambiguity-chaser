"""Set-level consistency check: do these requirements contradict each other?

Per-requirement scoring cannot see a contradiction between two requirements
that are each clear on their own (P1 req_25/req_34; Week 14 stress run). This
runs once over the whole set, before any per-requirement scoring.

Status values (what a caller reads, kept apart from the testability score):
  checked      the check ran and found no grounded conflict
  conflict     at least one grounded conflict (both quotes verbatim in source)
  not_checked  the check did not run, or its output never validated; never
               reported as "checked" on a failure
"""

import re
from dataclasses import dataclass, field

from graph import _call_validated
from schemas import ConsistencyReport, ground_conflicts

# Reasoning model: hidden reasoning tokens share max_tokens, and comparing a whole
# set uses more of them than scoring one requirement (2048 truncated in testing).
CONSISTENCY_MAX_TOKENS = 4096

with open("prompts/consistency_check_v1.txt", mode="r", encoding="utf-8") as f:
    CONSISTENCY_PROMPT = f.read()

with open("prompts/example_vs_rules_v1.txt", mode="r", encoding="utf-8") as f:
    EXAMPLE_PROMPT = f.read()

# A requirement "has an example" if it says so. A plain marker match, not a model
# call: cheap and visible, but it misses an example that never uses these words.
EXAMPLE_MARKER = re.compile(r"\b(example|e\.g\.|for instance|for example)", re.IGNORECASE)


@dataclass
class ConsistencyResult:
    status: str  # checked | conflict | not_checked
    conflicts: list[dict] = field(default_factory=list)  # grounded: these pause a run
    warnings: list[str] = field(default_factory=list)  # dropped claims, call problems
    call_attempts: int = 0

    def status_for(self, req_id: str) -> str:
        """checked/not_checked apply to every requirement in the set; conflict
        only to the ones a grounded conflict names."""
        if self.status == "conflict":
            involved = {rid for c in self.conflicts for rid in c["req_ids"]}
            return "conflict" if req_id in involved else "checked"
        return self.status

    def conflicts_for(self, req_id: str) -> list[dict]:
        return [c for c in self.conflicts if req_id in c["req_ids"]]


def check_consistency(requirements: dict[str, str]) -> ConsistencyResult:
    if len(requirements) < 2:
        # Nothing to compare: say so rather than claiming a check happened.
        return ConsistencyResult(status="not_checked", warnings=["fewer than two requirements"])

    listing = "\n".join(f"[{rid}] {text}" for rid, text in requirements.items())
    report, errors, attempts, _ = _call_validated(
        CONSISTENCY_PROMPT.format(requirements=listing), ConsistencyReport, max_tokens=CONSISTENCY_MAX_TOKENS
    )
    if report is None:
        return ConsistencyResult(
            status="not_checked", warnings=[f"check failed: {e}" for e in errors], call_attempts=attempts
        )

    grounded, dropped = ground_conflicts(report, requirements)
    warnings = [f"dropped ungrounded conflict {c.req_ids}: {why}" for c, why in dropped]
    return ConsistencyResult(
        status="conflict" if grounded else "checked",
        conflicts=[c.model_dump() for c in grounded],
        warnings=warnings,
        call_attempts=attempts,
    )


def check_examples(requirements: dict[str, str]) -> ConsistencyResult:
    """One call per requirement that contains an example: does the example's
    stated outcome follow from the rest of the set? Each call reasons over one
    example, so it stays inside the token budget a whole-set call exhausts.

    Catches only example-versus-rule contradictions; it says nothing about two
    plain rules that conflict. Status follows check_consistency: a failed call
    is never reported as checked, so a call failure with no conflict found is
    not_checked, and one failed call among successes still shows as a warning."""
    examples = [rid for rid, text in requirements.items() if EXAMPLE_MARKER.search(text)]
    if not examples or len(requirements) < 2:
        return ConsistencyResult(status="not_checked", warnings=["no requirement with an example"])

    grounded_all: dict[tuple[str, ...], dict] = {}
    warnings: list[str] = []
    attempts = 0
    failed = 0
    for rid in examples:
        rules = "\n".join(f"[{r}] {t}" for r, t in requirements.items() if r != rid)
        report, errors, n, _ = _call_validated(
            EXAMPLE_PROMPT.format(example_id=rid, example_text=requirements[rid], rules=rules),
            ConsistencyReport,
            max_tokens=CONSISTENCY_MAX_TOKENS,
        )
        attempts += n
        if report is None:
            failed += 1
            warnings += [f"[{rid}] check failed: {e}" for e in errors]
            continue
        grounded, dropped = ground_conflicts(report, requirements)
        warnings += [f"[{rid}] dropped ungrounded conflict {c.req_ids}: {why}" for c, why in dropped]
        for c in grounded:
            grounded_all.setdefault(tuple(sorted(c.req_ids)), c.model_dump())

    if grounded_all:
        status = "conflict"
    else:
        status = "not_checked" if failed else "checked"
    if failed and grounded_all:
        warnings.append(f"{failed} of {len(examples)} example checks failed; the set is only partly checked")
    return ConsistencyResult(
        status=status, conflicts=list(grounded_all.values()), warnings=warnings, call_attempts=attempts
    )
