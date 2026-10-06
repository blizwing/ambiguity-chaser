"""Per-branch test cases: one case per distinct branch of a requirement.

The graph's single-case path (generate_test_case) covers one path per
requirement. For a requirement with several statuses or clearance routes,
list the branches first, then write one case per branch whose outcome the
requirement actually states. A branch with no stated outcome becomes a
question for a human, not a guessed case (fabrication risk, CLAUDE.md).

Not wired into the graph yet: the single-case path stays the default until
this has been measured.
"""

from dataclasses import dataclass, field

from graph import _call_validated
from schemas import Branches, TestCase, spec_style_problem

MAX_BRANCHES = 6

with open("prompts/branches_v1.txt", mode="r", encoding="utf-8") as f:
    BRANCHES_PROMPT = f.read()

with open("prompts/testcase_v3.txt", mode="r", encoding="utf-8") as f:
    TESTCASE_PROMPT = f.read()


@dataclass
class BranchResult:
    status: str  # valid | needs_escalation
    cases: list[dict] = field(default_factory=list)  # {"branch", "test_case"}
    questions: list[str] = field(default_factory=list)  # branches with no stated outcome
    warnings: list[str] = field(default_factory=list)


def generate_branch_cases(requirement: str) -> BranchResult:
    listed, errors, _, _ = _call_validated(
        BRANCHES_PROMPT.format(requirement=requirement, max_branches=MAX_BRANCHES), Branches
    )
    if listed is None:
        return BranchResult(status="needs_escalation", warnings=[f"branch listing failed: {e}" for e in errors])

    result = BranchResult(status="valid")
    branches = listed.branches[:MAX_BRANCHES]
    if len(listed.branches) > MAX_BRANCHES:
        result.warnings.append(f"{len(listed.branches)} branches listed; kept the first {MAX_BRANCHES}")

    for b in branches:
        if not b.expected_stated:
            result.questions.append(f"What should happen when: {b.condition}? (branch '{b.name}')")
            continue
        scoped = f"{requirement}\nWrite the test case for this branch only: {b.condition}"
        detail, errs, _, warns = _call_validated(
            TESTCASE_PROMPT.format(requirement=scoped), TestCase, soft_check=spec_style_problem
        )
        if detail is None:
            result.status = "needs_escalation"
            result.warnings.append(f"branch '{b.name}' failed: {errs}")
            continue
        result.cases.append({"branch": b.name, "test_case": detail.model_dump()})
        result.warnings += [f"branch '{b.name}': {w}" for w in warns]
    return result
