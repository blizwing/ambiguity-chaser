# Handover — Laya R&D experiment (paused mid-run, 25 Sep 2026)

Written for a fresh Claude Code session with zero memory of the conversation
that produced this. Everything needed to resume is below — do not re-derive
it from scratch, and do not re-litigate decisions already made here without
flagging them to Pratham first.

## What this is

R&D spike evaluating whether **Laya** (`convaiinnovations/laya`, Apache 2.0,
self-hosted, open-weight) can replace or complement the DeepSeek-based
`score_testability` node in `graph.py`. This is the same shape of experiment
as the already-completed **Jev** aside (NOTES.md, parked — cloud-only/closed-
weight) and the **Instructor** experiment (branch `experiment/instructor-scoring`,
not merged). Laya was raised because it's pitched as an open-source,
self-hostable equivalent to Jev's "System One" typed-decision architecture —
which would remove the exact objection that killed the Jev idea.

**Status: PAUSED mid-run, at the user's explicit request ("halt everything").
No conclusion has been reached yet.** The full evaluation script is written,
debugged, and ready to run — it just hasn't been run to completion. Do not
report an adopt/don't-adopt verdict until it actually finishes and the
results are read.

## Where things are

- **Location:** a separate git worktree, sibling to the main repo, at
  `<local-path>/ambiguity-chaser-laya` (main repo is at the same path
  without `-laya`).
- **Branch:** `experiment/laya-scoring`, created off `main` at commit `27b9e45`.
  Not merged, not intended to be merged casually — same disposition pattern
  as `experiment/instructor-scoring` (kept as a historical record either way).
- **Venv:** a *dedicated* `.venv` was created inside this worktree
  specifically (not the shared one in the main repo's `.venv`) — deliberately,
  to avoid repeating the exact problem the Instructor experiment's write-up
  flagged (installing into the shared, non-branch-scoped `.venv` silently
  downgraded `openai` there). This worktree's `.venv` is fully isolated.
- **`.env`:** copied from the main worktree into this worktree (untracked,
  gitignored, never committed) purely so the real DeepSeek baseline scorer
  could be called for a real side-by-side comparison. Same key, same machine,
  same user — not a security concern, just noting it exists so it isn't a
  mystery. Fine to leave or delete.
- **requirements.txt:** `laya` has been added (last line) to reflect what's
  actually installed in this worktree's venv. This mirrors how the Instructor
  experiment pinned `instructor` immediately, with the same understanding
  that it may get reverted later if Laya isn't adopted (see that experiment's
  "Branch disposition" note in NOTES.md for the pattern to follow).

## How to resume — the one command that matters

```bash
cd "path/to/ambiguity-chaser-laya"
PYTHONPATH=. ".venv/Scripts/python.exe" scratch/scratch_laya_scoring.py
```

Run this **in the background** (it makes ~24 local Laya calls at ~0.4–0.5s
each, plus ~24 real DeepSeek API calls) and read the output file when it
completes. The `PYTHONPATH=.` is required — the script lives under
`scratch/` but imports repo-root modules (`llm_client`, `schemas`); without
it you'll get `ModuleNotFoundError: No module named 'llm_client'` (already
hit this once, already fixed by adding `PYTHONPATH=.`, not a real bug in the
script itself).

This exact invocation was started once already this session, got partway
through loading Laya (past the `Fetching 5 files` / calibration-warning
lines), and was killed via `TaskStop` before any requirement finished
running, because the user asked to halt. **Nothing in its output is a real
result yet** — just re-run it from scratch.

## The script: `scratch/scratch_laya_scoring.py`

Already written, in this worktree, untracked (new file, not yet committed —
that's expected; Claude never commits in this repo, see CLAUDE.md). Read it
before touching it — it's heavily commented with the *why* behind every
methodology choice. Do not modify the criterion wording or the `>= 0.5`
threshold without understanding why they were chosen (see "Methodology"
below) — both were deliberate, not arbitrary.

## Methodology (already agreed with the user this session — don't redesign it)

**Test set:** 8 hand-labeled requirements (function `REQUIREMENTS` in the
script), each labeled against the same 4 booleans `score_testability`
already computes (`has_measurable_condition`, `has_vague_qualitative_language`,
`has_ambiguous_scope`, `missing_precondition`). The original 3 canonical
texts (`clear`/`vague`/`middle` from Week 8 and the Instructor experiment)
are kept for continuity, plus 5 new ones added because the original 3 only
really exercised `has_measurable_condition` — the other three criteria
needed their own clean examples. The `middle` case ("responds in under 2
seconds in most cases") is **deliberately left unscored** (`None` for every
criterion) because Week 8 already found the current DeepSeek scorer
disagrees with itself run-to-run on that exact text (55 vs 70) — it's a
genuinely contested case, not a clean ground-truth one, so it's reported
separately rather than folded into an accuracy percentage.

**Fairness constraint:** Laya's 4 `noul` question instructions are worded
*verbatim* from `prompts/testability_score_v1.txt`'s own criterion
definitions — not reworded independently. This matters: rewording them
differently would make any accuracy gap uninterpretable (is it Laya's
architecture, or just worse-phrased questions?).

**Four things measured, all in the script's `SUMMARY` output:**
1. **Accuracy** vs. the hand-labels, per criterion and overall (excludes the
   contested `middle` case).
2. **Agreement with the current production scorer** — the real
   `call_deepseek_json` + `validate_response` path, unmodified, run on the
   same 8 texts, so it's a real side-by-side, not Laya-vs-a-guess.
3. **Determinism** — each text run 3x through Laya on identical input;
   since it's a non-autoregressive encoder forward pass (no sampling), exact
   repeatability is expected — the script flags any case where it *isn't*,
   which would itself be a notable finding.
4. **Calibration** — specifically flags any (requirement, criterion) pair
   where Laya was wrong **and** confidence was ≥0.8, because this project's
   core design principle (CLAUDE.md: "a confidently-wrong spec is worse than
   one that correctly paused to ask") applies exactly as much to a
   confidently-wrong *scoring signal* as to a confidently-wrong generated
   spec.

**Scoring integrity:** both arms (Laya-derived and DeepSeek-baseline) run
through the exact same unmodified `compute_testability_score()` from
`schemas.py` — nothing about the scoring arithmetic is forked or
reimplemented per arm, matching the discipline the Instructor experiment
already established.

**The `noul → bool` threshold is `>= 0.5`.** This was deliberately copied
from Laya's own internal convention (`laya.structured._project`'s exact line
for boolean fields), not invented independently — worth knowing when
interpreting borderline scores near 0.5.

## What's actually been confirmed so far (real, run results — not vendor claims)

These came from two smaller ad hoc probes run *before* the full script was
written, so they're real but not yet part of the full 8-requirement,
3-repeat evaluation:

- **Package install:** `pip install laya` → `laya-0.3.20` + deps. Real
  download was ~180MB, dominated by `torch-2.14.0` (124.1MB, CPU-only wheel,
  no CUDA variant pulled in). Also installed: `transformers-5.17.0`,
  `huggingface_hub-1.33.0`, `numpy-2.5.3`, `tokenizers`, and small support
  packages.
- **Model weights:** downloaded lazily on first `Router()`/`predict()` use,
  not at `pip install` time. Real size on disk: **~808MB total**
  (`model.safetensors` alone is ~843.6MB — actually check this arithmetic
  discrepancy is just `du` rounding/whole-block accounting, not a real
  inconsistency), cached at
  `~/.cache/huggingface/hub/models--convaiinnovations--laya/`. This is
  **fp16**, not fp32 — corrects an earlier guess (based on the Node/ONNX
  package's quoted ~1.7GB fp32 bundle) that turned out to be roughly 2x too
  high once actually measured.
- **Latency:** cold path (model not yet resident in this process's memory)
  costs ~14–44s depending on whether weights were already cached on disk.
  Once warm, steady-state is **~0.4–0.5s per `predict()` call** (which
  answers all questions passed to it in one forward pass — so 4 booleans in
  one call is still ~0.4–0.5s, not 4x that).
- **A real, load-time warning fires every time:** *"this checkpoint ships
  invalid temperatures or values outside [0.5, 5]; using
  choice:11+=0.1006 -> 0.5. Treat confidence from the affected entries as
  uncalibrated."* Investigated the actual shipped config
  (`rl_agent_config.json`, `temperature_by_options`) rather than taking the
  warning at face value: the broken bucket is specifically `choice:11+`
  (temperature 0.1006, clamped). **Our use case only ever uses `noul`
  questions (2 options), whose bucket (`noul:2`) has temperature 1.983 —
  within the valid [0.5, 5] range.** So this warning is very likely a red
  herring for this specific project's use case — flagged for the record,
  but should not be over-weighted as "the model is broken for us" without
  more evidence. (This conclusion came from reading the actual installed
  package source, `laya/common.py` and `laya/router.py`, and the actual
  shipped `rl_agent_config.json` — not from the pip warning text or any blog
  post.)
- **One real accuracy spot-check** (single criterion, single question, not
  the full script): on `has_measurable_condition` —

  | requirement | Laya P(true) | confidence | correct? |
  |---|---|---|---|
  | clear — "lock account after 5 failed attempts" | 0.62 | 0.62 | weak positive, should be near-certain |
  | vague — "should be fast" | 0.12 | 0.88 | correct (low) |
  | middle — "under 2 seconds in most cases" | **0.03** | **0.97** | **wrong, and confidently wrong** — a numeric threshold scored as the *least* measurable of the three |

  This is the finding that motivated writing the full 8-requirement,
  4-criterion script rather than concluding anything off 3 data points.

## System / compute facts (confirmed via actual OS queries, not estimated)

- CPU: Intel i5-1135G7, 4 cores / 8 threads, no discrete GPU.
- RAM: 31.7GB total. **Only 4.3GB was free at last check** — worth
  rechecking before a heavy run; the model itself needs a few GB (weights +
  activations), and if it's genuinely tight, close some apps first rather
  than assuming it'll be fine because total RAM is high.
- Free disk: 68.6GB — plenty of headroom for the ~1GB of package + weights.
- OS: Windows 11 Pro. Note: Hugging Face's cache-symlink optimization is
  disabled on this machine (Developer Mode not enabled / not running as
  admin) — harmless, just means slightly more disk use for caching, already
  accounted for in the ~808MB figure above.

## What Laya actually is, and how to use it correctly (read from the real installed source, not marketing copy)

- Package: `laya` (`.venv/Lib/site-packages/laya/`). Main entry point:
  `from laya import Router`.
- **Three checkpoints exist**, auto-routed by detected script/language:
  `english` (421M, ModernBERT-large, 512 tokens — what we're using),
  `multilingual` (322M, mmBERT-base, 1024 tokens, 100+ langs), and
  `typed-decisions` (421M, ModernBERT-large, 1024 tokens, fine-tuned on **4
  fixed synthetic workflows**: `agent_trace_observability`,
  `customer_service`, `invoice_processing`, `security_incidents`). The
  `typed-decisions` checkpoint is **not** relevant to us — it's only
  auto-selected when your question-id set exactly matches one of those 4
  workflows' fixed schemas, and even opting in explicitly wouldn't help,
  since it's fine-tuned on an unrelated domain.
- **Three question primitives:** `choice` (pick one named option), `score`
  (ordinal 0..N rubric level), `noul` (boolean, returns calibrated `P(true)`
  in the `noul` field, plus `confidence` = `max(p)`, the one the package's
  own docstrings say is the actually-calibrated quantity — see
  `answer_confidence` in `laya/common.py`).
- **Low-level API (what the script uses):**
  `router.predict(state, questions_dict)` → one forward pass answers every
  question in `questions_dict` at once. This is the documented low-level
  path shown directly in `Router`'s own class docstring in `router.py`.
- **There's also a higher-level schema path** (`laya.structured`:
  `Router.decide(state, schema=SomePydanticModel)`,
  `questions_from_pydantic`, `answer_to_pydantic`) that turns a Pydantic
  model straight into Laya questions. **Deliberately not used here**: it
  only supports bool/enum/bounded-int fields and explicitly rejects free
  strings (`SchemaError`) — our real `TestabilityScore` has a
  `reasoning: str` field, so it can't be passed directly. It also derives
  question wording from the Pydantic field's `description=`, which our
  `schemas.py` doesn't set — using it as-is would silently produce much
  weaker auto-generated instructions (e.g. *"Is `has_measurable_condition`
  true?"*) than the hand-worded ones taken from the real prompt file. This
  was a considered choice, not an oversight — don't "fix" it by switching to
  `decide()` without discussing that tradeoff first.
- **Compute/model lifecycle:** `Router()` itself is cheap and lazy — nothing
  loads until the first `predict()`/`load()` call for a given checkpoint.
  `max_loaded` (default 2) LRU-evicts checkpoints; `Router(preload=True)`
  front-loads everything if you want to avoid ever paying a cold-load cost
  mid-run. Batch scoring should probably use `predict_batch` /
  `route_batch` rather than looping `predict()` — **not yet tested or
  measured in this session**, worth doing if Laya clears the accuracy bar
  and throughput becomes the next question.

## Next steps for whoever picks this up

1. Re-run the full script (command above), in the background, and actually
   read its `SUMMARY` output — don't guess at what it would say.
2. Compare the full 8-requirement result against the single-criterion spot
   check above — does the "confidently wrong on `middle`" pattern hold up
   across more criteria/requirements, or was that one case unusual?
3. Apply the same bar this project has used before (Instructor experiment):
   a real, measured result — not "should work" — decides adopt or park.
4. Write the outcome up as a new NOTES.md aside, same pattern as the Jev and
   Instructor asides (goal / done / found / decision / branch disposition).
   Claude drafts it, Pratham reviews and validates before it's committed —
   per CLAUDE.md's NOTES.md authorship convention.
5. Branch disposition decision (keep as historical record vs. delete)
   follows the same logic as `experiment/instructor-scoring` — likely "keep,
   don't merge" either way, but that's Pratham's call once there's a result.
6. Per CLAUDE.md: Claude does not run `git add`/`git commit`/`git push` in
   this repo under any circumstances — give Pratham the exact commands to
   run himself, plain message, no co-author line.
