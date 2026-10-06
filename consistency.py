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

from dataclasses import dataclass, field

from graph import _call_validated
from schemas import ConsistencyReport, ground_conflicts

# Reasoning model: hidden reasoning tokens share max_tokens, and comparing a whole
# set uses more of them than scoring one requirement (2048 truncated in testing).
CONSISTENCY_MAX_TOKENS = 4096

with open("prompts/consistency_check_v1.txt", mode="r", encoding="utf-8") as f:
    CONSISTENCY_PROMPT = f.read()


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
