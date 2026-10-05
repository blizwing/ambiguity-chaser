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

## Status (as of 30 Sep 2026)

Weeks 6–11 of the roadmap are built and working: the scoring gate,
human-in-the-loop pause/persist/resume, the re-ask loop with a
max-iteration guard, and a tool-calling coverage check. Week 12
(embeddings + retrieval, replacing the keyword search behind the coverage
check) is next.

## What's built

```
requirement
    |
    v
score_testability <-------------------------+
    |                                        |
    +-- (score >= 86) --> check_coverage     |
    |                        |               |
    |                        +-- covered --> END (already_covered)
    |                        +-- not covered --> generate_test_case --> END
    |                                        |
    +-- (score < 86, re-asks left) --> generate_questions
    |                                        |
    |                                   ask_human  (interrupt; state persisted)
    |                                        |
    |                                        +--- answer folded in, re-score
    |
    +-- (score < 86, re-ask guard exhausted) --> mark_unresolved --> END
                                                  (status: needs_escalation)
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
- **`generate_questions` + `ask_human`** — for requirements that don't
  clear the gate, asks targeted questions instead of fabricating a spec.
  Rejects a schema-valid-but-empty response (`questions: []`) as
  untrustworthy rather than accepting it. Split into two nodes so the LLM
  call never re-runs on resume: `ask_human` holds only the `interrupt()`,
  and the checkpointer (SQLite, `graph_state.db`, keyed by a per-requirement
  `thread_id`) lets the run resume across process restarts.
- **Re-ask loop** — each human answer is appended to `human_answers`, folded
  into the requirement, and the requirement is re-scored. After
  `MAX_REASK_ITERATIONS` (2) rounds without passing, the graph routes to
  **`mark_unresolved`** (`status: needs_escalation`) instead of emitting a
  best-effort spec.
- **`check_coverage`** — before generating a spec, the model uses a
  `search_test_cases` tool (keyword overlap over `test_corpus.json`) to look
  for an existing test case that already covers the requirement. A "covered"
  verdict only counts if the cited test id is one the search actually
  returned. Bad model output at any step falls through to spec generation:
  a missed duplicate costs less than a requirement dropped by a broken check.
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

- **One status per caller behavior.** What a caller should do decides the
  status, not what went wrong (the cause goes in a detail field):

  | `status` | Caller does | Fields set |
  |---|---|---|
  | `needs_clarification` | show the questions, then resume | `clarifying_questions` |
  | `valid` | use the spec | `test_case` |
  | `already_covered` | link to the existing case | `coverage_match` |
  | `needs_escalation` | route to a human | `escalation_reason` (`unresolved_ambiguity` or `spec_generation_failed`) |
  | `invalid` / `invalid_json` | a node's own output failed; nothing to show | none |

  A paused run used to report `valid` with no spec, so a caller reading
  `test_case` got `None`. `tests/test_status_contract.py` pins this table.
  Keys with no value may be absent from a paused result; read with `.get`.

## Known limitations / open findings

- **Non-determinism isn't limited to generation.** Running the same
  unchanged clear requirement through the graph 5x produced a different
  testability score on one of five runs (100 vs. 85) — the ambiguity
  judgment feeding the routing decision varies run to run at
  `temperature=0`, not just the generated test case. Not fixed; can only
  be mitigated (e.g. majority-vote-across-N-calls), not eliminated.
- **Coverage search is keyword-only.** `search_test_cases` matches on word
  overlap, so a paraphrased requirement with no shared words won't find its
  existing test case. Week 12 replaces it with embeddings. Only the first
  tool call is handled (`tool_calls[0]`), and search results are folded into
  a prompt string rather than sent back as a `role: "tool"` message.
- **`thread_id` collisions.** The id is a hash of the requirement text, so
  two identical requirement strings submitted as separate runs share one
  thread. Accepted tradeoff.
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

## Experiments

Full standalone write-ups for research spikes that don't belong in the
day-by-day `NOTES.md` log — each is self-contained (motivation, method,
results, decision) and meant to be readable on its own, including outside
this repo.

- [`experiments/laya-fine-tuning.md`](experiments/laya-fine-tuning.md) —
  can a 421M open-weight self-hosted model (Laya) replace the DeepSeek
  judge behind `score_testability`? Zero-shot evaluation, root-cause
  investigation, a dead-end GPU rental provider, and 3 fine-tuning rounds
  (57% → 88% held-out accuracy). Branch `experiment/laya-scoring`.

## Repo layout

Normal descriptive filenames throughout (`graph.py`, `schemas.py`,
`llm_client.py`), deliberately not day-numbered — the day-by-day narrative
lives only in `NOTES.md`, keyed by date, never encoded into a filename
(see `CLAUDE.md` for why).

- `graph.py` — the LangGraph build described above.
- `schemas.py` — Pydantic models + scoring/validation logic.
- `llm_client.py` — DeepSeek API wrapper (JSON-mode and tool-calling).
- `tools.py` — `search_test_cases` and its tool schema.
- `test_corpus.json` — invented existing test cases the coverage check
  searches.
- `prompts/` — prompt text files, versioned by filename suffix (`_v1`).
- `scratch/` — throwaway hands-on exercises, not part of the graph.
- `experiments/` — full standalone write-ups for research spikes (see
  [Experiments](#experiments) above) — self-contained, unlike the
  day-by-day `NOTES.md` entries.
- `NOTES.md` — full day-by-day build log: goals, what got built, what was
  found (including dead ends and bugs), why it matters, raw files touched.
  The detailed record; this README is the rollup.
- `ROADMAP.md` — week-level plan for this phase.
- `CLAUDE.md` — project conventions for AI-assisted sessions in this repo.

## Related repos

- [eval-harness](https://github.com/blizwing/eval-harness) — Phase 1
  (AI Quality / Evaluation), complete, public.
- Phase 3 (Agent Eval Layer, fine-tuned classifier) — later, separate repo.
