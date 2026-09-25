# CLAUDE.md

Project context for Claude Code sessions in this repo.

## What this is
A LangGraph agent that reads a plain-English software requirement, scores how
testable/unambiguous it is, and either emits a structured test spec or raises
clarifying questions and pauses for a human answer before continuing. Phase 2
of a three-project, six-month plan (full plan: `ROADMAP.md` in this repo,
copied from the master roadmap in `eval-harness`).

- **P1 — Eval Harness** (sister repo, public, complete):
  https://github.com/blizwing/eval-harness. Proved AI Quality / Evaluation.
  11 Aug – 13 Sep 2026.
- **P2 — Ambiguity Chaser** (this repo): proves agentic dev + GenAI.
  Sep – Nov 2026.
- **P3 — Agent Eval Layer** (fine-tuned classifier, separate repo, later):
  proves QA for non-deterministic systems. Dec – Jan.

Repo: `blizwing/ambiguity-chaser` (public).

## Why this project exists
Directly closes a gap P1 found and explicitly parked as out of scope for
itself: a per-requirement judge/generator architecture cannot catch a
contradiction between two requirements that are each individually
unambiguous (see `eval-harness` NOTES.md, Day 17 — the `req_25`/`req_34`
device-swap-ordering contradiction, sourced from a real disagreement between
two stakeholder groups). Catching that needs something that reasons over the
requirement set as a whole, not one requirement at a time. That's this
project.

## File/folder naming: deliberately different from eval-harness
`eval-harness` used `DayN_*`-prefixed files and folders throughout, which
worked but left every import, the CI workflow, and every cross-reference
tied to a day number rather than what the file actually does — flagged as a
backlog item there (see `eval-harness/BACKLOG.md`, "Split repo into clean
main + learning-log branch") rather than fixed, since fixing it mid-build
would have been its own risky rename exercise.

**This repo starts clean instead:** normal descriptive filenames
(`loader.py`, `agent.py`, `graph.py`, not `Day6_loader.py`). The day-by-day
narrative lives in `NOTES.md` only, keyed by date/week, never encoded into a
filename. If per-day experiment artifacts need their own folder, name the
folder for what it contains, not the day number.

## Carried-over findings from P1 (still true here, not re-derived)
- **Non-determinism, not exact-match.** `temperature=0` is not fully
  deterministic, and the degree differs by API surface (OpenAI-schema vs
  Anthropic-schema, confirmed empirically in P1 Day 2). Any eval/regression
  check on this agent's output needs pass-rate thresholds across multiple
  runs, not exact-match diffing.
- **Fabrication risk.** A model asked for something it can't know will
  invent a plausible-looking value rather than refuse or return null (P1 Day
  4). Directly relevant to this agent's core decision — "emit a spec" vs
  "ask a clarifying question" — since a confidently-wrong spec is worse than
  one that correctly paused to ask.
- **Temperature/config must always be explicit**, never inherited from a
  library or provider default (P1 Day 23 caught a silent `temperature=1.0`
  default this way).
- **Unify statuses around caller behavior, not failure-cause granularity**,
  when designing error/status types — don't split a status just because the
  underlying causes differ, if the caller's handling doesn't.
- **Grader/self-output integrity matters as much as model-output
  integrity.** P1's Day 24 `ScoreIntegrityError` closed a real gap: assert
  on your own tool's output, not just the model's. Same discipline applies
  to whatever this agent reports about its own testability scoring.

## Where things live
Intentionally sparse today — filled in as Week 6+ actually gets built,
per the roadmap's own note: "daily detail comes when you get there."

## Roadmap
Week-level plan for this phase is in `ROADMAP.md` in this repo (copied from
the master roadmap). Full three-phase context and the complete P1 build log
live in the `eval-harness` repo, not duplicated here beyond what's needed to
work in this one.

## Workflow conventions (carried from eval-harness — confirm/adjust as they come up)
- **All actual repo work happens on Pratham's machine.** When Claude Code
  has direct file/execution access to this repo (as in a local session),
  Claude edits and runs things directly rather than only handing over
  commands — that distinction was clarified partway through P1 (see
  `eval-harness` NOTES.md, Day 32) after an earlier session read the
  no-sandbox-access convention too literally. Read-only verification is
  always fine regardless.
- **Commit workflow is synced with `eval-harness` (resolved 13 Sep 2026):**
  Claude never runs `git commit` or `git push` itself in this repo — it
  gives Pratham the exact `git add`/`git commit -m "..."` commands to run
  himself, with a plain commit message and no `Co-Authored-By: Claude`
  line. This matches the stricter rule already in force in `eval-harness`
  (established there after a specific mistake). This resolves the "Known
  open question" below in favor of the stricter rule — it now applies here
  too, not just in `eval-harness`.
- **Daily workflow:** verify the prior day's work is actually present
  before starting a new day; state that day's objective and DONE WHEN from
  `ROADMAP.md`, flag upfront whether it's a "Pratham writes first draft"
  (new concept/judgment call) day or a "Claude writes first draft, Pratham
  reviews/runs" (repetitive plumbing) day, get agreement before starting;
  build/guide accordingly; after DONE WHEN is confirmed, run an
  end-of-day understanding check on the WHY behind decisions, not the WHAT.
- **NOTES.md authorship:** Claude drafts the day's entry; Pratham reviews,
  edits, and validates before committing.
- **Code ownership split:** Pratham writes domain judgment, the actual
  agent-behavior design calls, and first-draft code on judgment-heavy days.
  Claude scaffolds plumbing, wrappers, and repetitive structure. Claude
  flags inconsistencies; Pratham makes the calls.
- **GitHub verification pattern:** `curl` against
  `raw.githubusercontent.com/{user}/{repo}/{branch}/{path}` for live file
  content — avoid `api.github.com` (60 req/hr unauthenticated limit). To
  confirm commits landed, re-clone with `git clone --depth 1` rather than
  relying on `git pull`.
- **No PII or secrets in git, ever (added 13 Sep 2026).** This repo is
  public. Before staging anything — especially a broad `git add`, a new
  untracked file, or any file whose contents Claude hasn't actually
  read — check its contents for API keys/tokens, credentials, real
  personal data (names, emails, phone numbers tied to real people), or
  any other sensitive value. Never commit a real `.env`; only
  `.env.example` with blank/placeholder values. If something sensitive is
  found staged or already committed, stop and flag it to Pratham rather
  than silently fixing or force-pushing over it — history rewrites need
  his explicit call.
- **Public-repo precautions extend to third-party tools/services, not just
  `git` (added 26 Sep 2026).** Same "this repo is public" reasoning as
  above, applied wherever data or execution crosses outside this machine:
  - **MCP servers that execute external code** (e.g. `uvx`/`npx` pulling
    straight from a git URL, as with the Colab MCP setup) — only add ones
    from a verified/official source (confirmed against the vendor's own
    repo/org, not just a search result), and prefer the narrowest useful
    `claude mcp add` scope. Personal dev tools with no project-specific
    config belong at `user` scope, not `project` — `project` scope writes
    to `.mcp.json`, which is committed and would publish the server config
    (and any args/env passed to it) to the public repo.
  - **Anything uploaded to an external service** (Colab, Drive, HF Hub,
    JarvisLabs, etc.) — treat it as potentially as public as this repo.
    Check scratch/training-data files for secrets or real personal data
    before they leave the machine, same as the git-staging check above,
    even though the destination isn't git.

## Known open question — RESOLVED 13 Sep 2026
Was: whether `eval-harness`'s stricter commit-workflow rule (give commands
only, never execute, no co-author line) should apply here too. Resolved:
yes — see the commit-workflow bullet above. This applies only to the
commit/push rule; the broader Day-32 direct-execution convention (Claude
edits and runs non-commit things directly in a local session) is unchanged.
