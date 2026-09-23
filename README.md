# ambiguity-chaser

A LangGraph agent that reads a plain-English software requirement, scores
how testable/unambiguous it is, and either emits a structured test spec or
raises clarifying questions and pauses for a human answer before
continuing.

Phase 2 of a three-project, six-month plan moving from AI Quality into
agentic GenAI engineering (Sep–Nov 2026). Closes a gap
[eval-harness](https://github.com/blizwing/eval-harness) (Phase 1, complete)
found and explicitly parked as out of scope for itself: a per-requirement
judge/generator can't catch a contradiction between two requirements that
are each individually unambiguous. Full three-phase context and the
complete Phase 1 build log live in that repo.

## Status (as of 23 Sep 2026)

Weeks 6–8 of the roadmap are built and working; Week 9 (human-in-the-loop
interrupt/resume) is in progress — the pause/persist/resume mechanics are
proven in a scratch script (`scratch/scratch_interrupt.py`), not yet wired
into the real graph below.

## What's built

```
requirement
    |
    v
score_testability  -->  (score >= 86) --> generate_test_case  --> END
    |
    (score < 86)
    |
    v
ask_clarifying_questions --> END   # will become a real pause once Week 9 lands
```

- **`score_testability`** — asks the model to report four boolean facts
  about the requirement (`has_measurable_condition`,
  `has_vague_qualitative_language`, `has_ambiguous_scope`,
  `missing_precondition`) plus reasoning. Python, not the model, turns
  those into a 0–100 score: `has_measurable_condition` is a hard gate (fail
  it, score is 0), each remaining soft criterion present costs 15 points.
  Threshold to pass is **86, not 85** — deliberate, so that a single soft
  failure (which scores exactly 85) never clears the gate.
- **`generate_test_case`** — for requirements that clear the gate, produces
  a validated, structured `TestCase` (title, preconditions, steps, expected
  result, priority).
- **`ask_clarifying_questions`** — for requirements that don't, asks
  targeted questions instead of fabricating a spec. Rejects a
  schema-valid-but-empty response (`questions: []`) as untrustworthy rather
  than accepting it.
- Every LLM response is run through `validate_response` (Pydantic), which
  never raises — malformed model output is expected input here, not a bug.

Runs on the **DeepSeek API** (`deepseek-flash`, requested explicitly — the
`deepseek-chat` alias is deprecated and silently reroutes) via the
OpenAI-compatible SDK, for cost reasons.

## Key decisions and why

- **Pydantic `BaseModel` for graph state, not `TypedDict`.** LangGraph
  doesn't enforce `TypedDict` shapes at runtime; this project's whole
  premise (score → emit spec or ask, never fabricate) can't tolerate
  silent state drift.
- **Model reports facts, code does arithmetic.** The scorer returns
  booleans + reasoning; `compute_testability_score` does the deduction
  math in Python. Never trust the model to self-report a number it could
  invent a plausible-looking value for — same discipline as eval-harness's
  `ScoreIntegrityError`.
- **Threshold is 86, not 85.** Boundary-arithmetic bug found and fixed same
  session: `score >= 85` still let one soft failure through, since one
  soft failure scores exactly 85.
- **A scorer that fails schema validation forces a 0, not a crash** — a
  defensible fail-safe (can't confidently score it, don't confidently
  generate a spec either), though this currently makes "score is
  genuinely 0" indistinguishable from "the scorer's own output was
  malformed" in the final state (`status` gets overwritten by whichever
  node runs next). Left open, not yet fixed.

## Known limitations / open findings

- **Non-determinism isn't limited to generation.** Running the same
  unchanged clear requirement through the graph 5x produced a different
  testability score on one of five runs (100 vs. 85) — the ambiguity
  judgment feeding the routing decision varies run to run at
  `temperature=0`, not just the generated test case. Not fixed; can only
  be mitigated (e.g. majority-vote-across-N-calls), not eliminated.
- **`ask_clarifying_questions` currently dead-ends** — it generates
  questions and the graph just ends. Week 9's actual task is making that a
  real pause: `interrupt()` + a checkpointer + a per-requirement
  `thread_id`, so "score → ask → *(human answers later)* → resume →
  generate real spec" becomes one continuous run instead of two
  disconnected halves.
- **Evaluated and parked: TypeSafe AI's Jev ("System One" model) as a
  faster/cheaper judge for `score_testability`.** Architecturally a
  plausible fit (calibrated typed decisions vs. free-text generation), and
  genuinely cheap ($0.042/M input tokens, confirmed first-hand against
  TypeSafe's own docs — a third-party playground had quoted 6–10x that).
  Not adopted: cloud-only/closed-weight with no self-host option, ~1 week
  old with no track record, and — per TypeSafe's own published
  limitations — no guarantee that logically-equivalent questions produce
  consistent outputs, i.e. the same non-determinism problem above, just
  faster and cheaper, not more reliable. Full writeup in `NOTES.md`,
  Week 9 aside.

## Repo layout

Normal descriptive filenames throughout (`graph.py`, `schemas.py`,
`llm_client.py`), deliberately not day-numbered — the day-by-day narrative
lives only in `NOTES.md`, keyed by date, never encoded into a filename
(see `CLAUDE.md` for why).

- `graph.py` — the LangGraph build described above.
- `schemas.py` — Pydantic models + scoring/validation logic.
- `llm_client.py` — DeepSeek API wrapper (JSON-mode calls).
- `prompts/` — prompt text files, versioned by filename suffix (`_v1`).
- `scratch/` — throwaway hands-on exercises, not part of the graph.
- `NOTES.md` — full day-by-day build log: goals, what got built, what was
  found (including dead ends and bugs), why it matters, raw files touched.
  The detailed record; this README is the rollup.
- `ROADMAP.md` — week-level plan for this phase.
- `CLAUDE.md` — project conventions for AI-assisted sessions in this repo.

## Related repos

- [eval-harness](https://github.com/blizwing/eval-harness) — Phase 1
  (AI Quality / Evaluation), complete, public.
- Phase 3 (Agent Eval Layer, fine-tuned classifier) — later, separate repo.
