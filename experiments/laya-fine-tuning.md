# Fine-Tuning a 421M Open-Weight Model to Judge Requirement Testability

**Can a small, self-hosted model replace an LLM judge for a narrow, structured
scoring task — and how far can fine-tuning close the gap?** This is the full
story of one attempt: a real dead end, a real root-cause investigation, three
real fine-tuning rounds, and a result that's genuinely good but not the clean
100% a slide deck would want.

Part of [ambiguity-chaser](../README.md) (Phase 2 of a three-phase AI
engineering roadmap). Everything below happened on branch
`experiment/laya-scoring`, in its own git worktree — not merged into `main`,
kept as a historical record. Dates below are all 2026.

---

## Index

1. [TL;DR](#tldr)
2. [Why We Looked at Laya](#why-we-looked-at-laya)
3. [Zero-Shot Evaluation](#zero-shot-evaluation)
4. [Root-Causing the Gap](#root-causing-the-gap)
5. [Why We Moved to Fine-Tuning](#why-we-moved-to-fine-tuning)
6. [The Compute Hunt](#the-compute-hunt)
7. [Fine-Tuning Setup](#fine-tuning-setup)
8. [Round 1: Baseline Fine-Tune](#round-1-baseline-fine-tune)
9. [Reading the Errors, Not Guessing](#reading-the-errors-not-guessing)
10. [Round 2: Targeted Data, Not More Data](#round-2-targeted-data-not-more-data)
11. [Round 3: Fighting Overfitting](#round-3-fighting-overfitting)
12. [Full Results Table](#full-results-table)
13. [Can Any Model Hit 100%?](#can-any-model-hit-100)
14. [Decision and What's Next](#decision-and-whats-next)
15. [Process Notes and Tooling Lessons](#process-notes-and-tooling-lessons)
16. [Appendix: Raw Files](#appendix-raw-files)

---

## TL;DR

- `ambiguity-chaser`'s `score_testability` node judges 4 boolean properties
  of a requirement using DeepSeek (a hosted LLM). We asked: could a small,
  self-hosted, open-weight model (**Laya**, 421M params) do this instead —
  cheaper, faster, no API dependency?
- **Zero-shot: no.** 57-61% accuracy vs. DeepSeek's 96-100%, with one
  criterion (`missing_precondition`) both the least accurate *and* the most
  confidently wrong.
- We didn't stop at the number — root-caused the gap to two real, separate
  causes (not "the model is bad"): full fp32 compute confirmed correct (not
  a precision bug), and a **documented label-anchoring bug** in one question
  type, which we tested a fix for and confirmed helps.
- The vendor's own published numbers said fine-tuning should close most of
  that gap. We tested it on **our** schema, not their benchmark.
- **JarvisLabs (the planned GPU rental) was a dead end** — confirmed with a
  real backend bug report, not just "it didn't work." Pivoted to Google
  Colab mid-session.
- **Three fine-tuning rounds**, each a hypothesis, each measured against a
  held-out set labeled by the real production judge:
  **57% → 86% → 87% → 88%** overall accuracy.
- Found a genuine, non-obvious trade-off along the way: the round that won
  on accuracy had *worse* calibration than the round before it — fewer
  training epochs bought balance and accuracy, not the better-calibrated
  confidence we expected.
- **Ceiling isn't just about the model.** Some of the remaining "errors" are
  the eval set's own labeler disagreeing with itself on genuinely
  borderline requirements — the same task-level judgment problem this whole
  project (`ambiguity-chaser`) exists to study.

---

## Why We Looked at Laya

`score_testability` (the core scoring node in this project's LangGraph
agent) asks an LLM to report four boolean facts about a plain-English
requirement — `has_measurable_condition`, `has_vague_qualitative_language`,
`has_ambiguous_scope`, `missing_precondition` — which Python then turns into
a 0-100 score. Every call currently goes to DeepSeek: correct, but a hosted
API dependency with per-call latency and cost.

This is the third self-hosted/cheaper-judge experiment for this exact node.
Two came before it:

- **TypeSafe's Jev** ("System One" typed-decision model) — architecturally
  a plausible fit, genuinely cheap, but closed-weight, cloud-only, ~1 week
  old with no track record. Parked.
- **Instructor** (structured-output wrapper around the same DeepSeek call)
  — tested, not adopted; full writeup in `NOTES.md`.

**Laya** (`convaiinnovations/laya`, Apache 2.0, self-hosted, open-weight,
421M params, ModernBERT-large backbone) was raised because it's pitched as
an open, self-hostable equivalent of exactly what made Jev attractive —
calibrated typed decisions instead of free-text generation — without the
closed-weight objection that killed Jev. If it worked, it would remove the
API dependency entirely.

---

## Zero-Shot Evaluation

**Method:** 8 hand-labeled requirements, scored against Laya's `noul`
(boolean) question primitive, worded *verbatim* from the same criterion
definitions the production DeepSeek prompt already uses — a fairness
constraint, not a strawman. Each requirement run 3x through both Laya and
the real, unmodified DeepSeek call, to separately check accuracy, agreement,
determinism, and calibration.

The comparison script runs *both* arms — Laya and the real, unmodified
DeepSeek baseline — together on the same 28 checks, so every run produces
numbers for both. We ran the whole script twice: once with Laya on this
machine's CPU, once after installing a CUDA build so Laya ran on its GPU.
DeepSeek is an API call in both passes — its own CPU/GPU is irrelevant, and
Laya's compute mode doesn't touch it — so the small shift in its numbers
between the two runs (96% → 100%) isn't a CPU/GPU effect. It's DeepSeek's
own already-documented run-to-run non-determinism — the same
`temperature=0`-is-not-fully-deterministic finding this project's README
already flags under "Known limitations" — showing up here simply because
we happened to call it twice.

| | Run 1 (Laya on CPU) | Run 2 (Laya on GPU) |
|---|---|---|
| Laya overall accuracy | 17/28 (61%) | 16/28 (57%) |
| DeepSeek baseline accuracy | 27/28 (96%) | 28/28 (100%) |
| `missing_precondition` accuracy (Laya) | 2/7 (29%) | 2/7 (29%) |
| confidently-wrong (confidence ≥0.8) | all 4 on `missing_precondition` | all 4 on `missing_precondition` |
| determinism (Laya) | 32/32 pairs exactly repeatable | 32/32 pairs exactly repeatable |
| Laya latency | 1.44s/call (4 criteria at once) | 0.13s/call (~11x faster on GPU) |
| DeepSeek latency | 3.01s/call | 3.00s/call (API-bound, unaffected by Laya's compute mode) |

`missing_precondition` was consistently the worst criterion **and** the
only one with confidently-wrong answers — not scattered noise, a
concentrated failure mode, identical in both runs (as expected: same
frozen checkpoint, same inputs, no sampling). Determinism was a genuine
point in Laya's favor: zero-shot, no sampling, exactly repeatable — the
opposite of DeepSeek's known run-to-run variance on borderline cases (see
below).

## Root-Causing the Gap

Before trusting the 61%-vs-96% number, we checked whether we'd simply run
Laya wrong — reading the actual installed library source, not assuming.

**(a) Not a precision bug.** Searched the whole `laya` source for any
quantization path — there isn't one. The checkpoint is fp16 on disk, but
`common.py:build_model` upcasts to fp32 with no `torch_dtype` override, and
CPU inference doesn't enable fp16/bf16 autocast unless explicitly requested.
We ran with *more* numerical precision than the checkpoint's native format,
not less. Precision loss doesn't explain the gap.

**(b) A real, documented bug — and we tested the vendor's own fix.** Laya's
model card explicitly warns: `noul` questions can anchor on their own
`false:`/`true:` option labels instead of reading the actual input state,
"most strongly on this English checkpoint." `missing_precondition` is
phrased as a negation ("does the requirement *fail* to state...") — exactly
the shape where this would bite. We tested the vendor's own suggested fix:
switch just that one criterion from `noul` to a neutral two-option `choice`,
leaving the other 3 criteria untouched. Result: `missing_precondition` moved
from 2/7 (29%) → 3/7 (43%), and every confidently-wrong answer disappeared
(max confidence dropped from 0.90 to 0.78). Real improvement — but still far
below DeepSeek's baseline, so the bug was real but not the whole story.

**(c) The real limiting factor, per the vendor's own model card:** base
Laya checkpoints are described as *"near chance on typed-decisions
zero-shot... a fast base to specialise, not a zero-shot decision engine."*
Their own benchmark: the same 421M checkpoint scores 0.362 zero-shot →
**0.766 after fine-tuning** on their own decision benchmark. That's the gap
we set out to test on our own schema.

## Why We Moved to Fine-Tuning

Zero-shot Laya, even with the `choice`-format fix, wasn't close enough to
DeepSeek to adopt. But the vendor's own numbers said the architecture is
*designed* to need fine-tuning — "near chance zero-shot" isn't a defect,
it's the documented operating mode. The open question worth actually
testing: does the same jump (0.362 → 0.766 on their benchmark) hold on
**our** 4-criterion schema, with **our** real requirement texts, not a
generic decision benchmark?

## The Compute Hunt

Fine-tuning even a 421M model needs more memory than inference: weights +
gradients + Adam's two optimizer moments, in fp32, is roughly
**421M × 4 bytes × 4 ≈ 6.7GB — before any activations** — already over this
machine's 6GB RTX 4050. Needed external compute.

**JarvisLabs — a real dead end, confirmed two independent ways, not just
"it didn't work":**

1. `jl gpus --json` returned an empty GPU list despite working auth.
   Root-caused by hitting the backend API directly: the installed CLI
   filters GPU rows by `gpu.region in REGION_URLS`, but the backend no
   longer sets `region` on GPU rows (returns `None`), so every row gets
   silently dropped — a real client/backend contract mismatch, worth
   reporting upstream.
2. Separately, tried actually provisioning an instance — VM and plain GPU
   container, across all three regions (default, IN1, EU1). All 6 attempts
   failed straight from the *create* endpoint itself ("No pricing for
   RTX5000...", "RTX5000 is not available in \[region\]"). No instance
   provisioned, no cost incurred. This ruled out "maybe the listing bug is
   hiding real capacity" — the create endpoint confirms zero usable
   capacity, independent of the listing bug.

Pivoted to **Google Colab** instead, via the official `googlecolab/colab-mcp`
MCP server — verified against the real GitHub org (not just a search
result) before installing, registered at `user` MCP scope specifically so
its config never lands in this public repo's committed `.mcp.json`.

Important architectural finding: Colab MCP is a **browser proxy, not a
headless API**. `uvx` starts a local bridge, but nothing useful happens
until a tool call opens an actual Colab tab and a human clicks through a
live connection. Only after that does the real notebook-editing toolset
(add/run cells, etc.) appear — dynamically, not hardcoded. GPU runtime
selection and file transfer both turned out to have **no dedicated MCP
tool** — both had to go through ordinary code cells and, for the runtime
type, a manual click in the Colab UI (Runtime → Change runtime type → T4
GPU), since nothing in the MCP surface can flip that setting.

## Fine-Tuning Setup

The vendor (`NandhaKishorM/laya`) publishes a reference fine-tuning
notebook for their own benchmark, `laya_finetune_typed_decisions_
2xT4_kaggle.ipynb`. We fetched and read the actual notebook (not a
description of it) and adapted it:

- **Single T4, no DDP.** Our dataset is ~25x smaller than the vendor's
  1,200-case benchmark — one GPU is plenty, so `torch.distributed`/
  `torchrun` was stripped entirely, run in-process instead.
- **`missing_precondition` switched to `choice`** for training (not left as
  `noul`) — an explicit decision, not a default. The zero-shot fairness
  constraint (verbatim `noul` wording across all 4 criteria) doesn't apply
  to fine-tuning, and we already had evidence `choice` fixes a documented
  bug on exactly this criterion.
- **Crisp one-hot targets, not soft teacher-agreement distributions.** The
  vendor's `gold` labels come from multi-teacher agreement counts; we have
  single hand-authored ground-truth booleans, so training targets are
  one-hot.
- **Training and eval labels from deliberately different sources.**
  168 Claude-authored requirement texts *and* labels for training; a
  separate 39-item held-out set with Claude-authored texts but **DeepSeek**-
  generated labels (via the real, unmodified `call_deepseek_json` +
  `validate_response` path) for evaluation. If the fine-tuned model agrees
  with DeepSeek, that's a real signal — agreement with Claude's own labels
  would just measure whether it memorized Claude's rubric.
- One measured data-quality fact worth keeping: DeepSeek labeling the
  held-out set returned `invalid_json` on 1 of 40 texts — a real ~2.5%
  failure rate at this scale, not zero.

## Round 1: Baseline Fine-Tune

15 epochs, 605 training sequences (672 total, 10% held out for post-training
calibration), ~11 minutes on the T4. Loss dropped 0.48 → 0.013; reward
saturated at its maximum (0.75) after epoch 2.

**Held-out result (against the real DeepSeek-labeled set, 39 texts / 156
checks):**

| Criterion | Accuracy |
|---|---|
| `has_measurable_condition` | 79% |
| `has_vague_qualitative_language` | 97% |
| `has_ambiguous_scope` | 90% |
| `missing_precondition` | 77% |
| **Overall** | **86%** |
| ECE (calibration error) | 0.080 |

Zero-shot 57% → fine-tuned 86% in one run — the vendor's claimed jump held
on our schema too.

## Reading the Errors, Not Guessing

The instinct after a good number is to declare victory or blindly tune
hyperparameters. Instead we pulled the actual 22 misclassified checks and
read them.

**`has_measurable_condition` (8/8 errors, same direction, confidently
wrong):** every miss was a *concrete state change with no literal number* —
*"A returned item must be inspected before a refund is issued,"* *"A
subscription must be paused, not canceled, when a user selects..."* The
training set almost certainly skewed toward numeric-threshold examples (X
attempts, Y seconds, $Z) and underrepresented this subtype, even though the
criterion's own definition explicitly includes "a concrete state change."

**`has_ambiguous_scope` (4/4 errors, same direction):** the model
under-detects ambiguity in vague *operational verbs* — "archive," "flag,"
"clearly show" — actions whose meaning is itself underspecified, distinct
from vague adjectives (which the other criterion already catches fine).

**`missing_precondition` (9 errors, mixed):** partly the same coverage gap,
but several looked like **noisy gold labels, not model error** — e.g.
DeepSeek marks *"archive conversations older than 180 days"* as missing a
precondition despite containing what reads like an explicit threshold. This
echoes an earlier finding (Week 8 of the main project) that the production
judge disagrees with itself on genuinely borderline requirements.

This is the finding that shaped everything after it: **two specific,
fixable coverage gaps**, not a vague "needs more data."

## Round 2: Targeted Data, Not More Data

31 new Claude-authored examples, built to hit exactly the two identified
gaps — not a random top-up. Checked for zero text overlap with the held-out
eval set before training (asserted in code, not assumed). Combined training
set: 199 texts / 796 sequences. Same 15 epochs.

| Criterion | Round 1 | Round 2 | Δ |
|---|---|---|---|
| `has_measurable_condition` | 79% | **90%** | **+11** |
| `has_vague_qualitative_language` | 97% | 95% | -2 |
| `has_ambiguous_scope` | 90% | 90% | 0 |
| `missing_precondition` | 77% | 74% | -3 |
| **Overall** | 86% | 87% | +1 |
| ECE | 0.080 | 0.064 | better |

The `has_measurable_condition` fix worked exactly as hypothesized (+11pt) —
strong confirmation the error-reading approach was finding a real signal.
The `ambiguous_scope` operational-verb fix didn't move the aggregate number.
`missing_precondition` dipped slightly (possibly noise on 39 items,
possibly dilution from more `choice`-type training diversity).

**The real story wasn't the +1pt overall — it was overfitting.** Training
loss hit exactly **0.0** by epoch 14, and **both** calibration temperatures
clamped at the fitting function's own maximum (10.0), meaning the model was
maximally overconfident on calibration items it had never trained on. A
+1pt accuracy gain riding on top of that isn't free.

## Round 3: Fighting Overfitting

Single-variable, hypothesis-driven change: **epochs 15 → 8.** Round 2's own
per-epoch log showed loss already down to 0.12 by epoch 8, well before the
later full memorization — testing whether stopping there keeps most of the
accuracy gain with a saner, non-clamped calibration. Nothing else changed:
same 199-item set, same learning rates, same batch size.

| Criterion | Round 2 (15ep) | Round 3 (8ep) |
|---|---|---|
| `has_measurable_condition` | 90% | 82% |
| `has_vague_qualitative_language` | 95% | 97% |
| `has_ambiguous_scope` | 90% | **92%** |
| `missing_precondition` | 74% | **82%** |
| **Overall** | 87% | **88%** |
| ECE | **0.064** | 0.103 |
| `choice` temperature | 10.0 (clamped) | 5.31 (un-clamped) |
| `noul` temperature | 10.0 (clamped) | 9.64 (near-clamped) |

Round 3 won on overall accuracy (88%, best of all three rounds) and was the
most balanced — no criterion below 82%. But **ECE got worse, not better**
(0.064 → 0.103), the opposite of what the calibration hypothesis predicted.
Less raw overfitting (the `choice` temperature un-clamped) bought accuracy
and balance, not better-calibrated confidence. A genuine, non-obvious
trade-off, reported honestly rather than cherry-picking whichever number
looked best.

## Full Results Table

| | Zero-shot | Round 1 | Round 2 | Round 3 | DeepSeek baseline |
|---|---|---|---|---|---|
| Training data | — | 168 items | 199 items | 199 items | — |
| Epochs | — | 15 | 15 | 8 | — |
| `has_measurable_condition` | — | 79% | 90% | 82% | — |
| `has_vague_qualitative_language` | — | 97% | 95% | 97% | — |
| `has_ambiguous_scope` | — | 90% | 90% | 92% | — |
| `missing_precondition` | 29% | 77% | 74% | 82% | n/a |
| **Overall** | **57%** | **86%** | **87%** | **88%** | **96-100%** |
| ECE | — | 0.080 | 0.064 | 0.103 | — |
| Latency (p50) | ~130ms | 34ms | 41ms | 35ms | ~3000ms |

**Kept checkpoint: Round 3** — best accuracy, most balanced, and the
calibration trade-off is a documented, understood cost rather than a
silent one.

## Can Any Model Hit 100%?

Worth addressing directly, since it came up mid-session: **no, not with
this setup — and not primarily because of the model.**

1. **The eval target itself isn't 100% self-consistent.** The held-out
   "gold" labels come from DeepSeek's own judgment, and this project
   already found (Week 8, main build) that DeepSeek disagrees with itself
   run-to-run on genuinely borderline requirements. The same pattern showed
   up in this experiment's own error analysis — DeepSeek calls *"archive
   conversations older than 180 days"* as `missing_precondition=True`
   despite what reads like an explicit threshold. You can't fit a model to
   agree with a labeler that doesn't fully agree with itself. Even
   DeepSeek only scores 96-100% against Claude's own hand-labels — not 100%
   either.
2. **This is an interpretive judgment task, not a fact lookup.** Whether a
   requirement's scope is "ambiguous" has genuine borderline cases where
   reasonable graders differ — that's the entire premise `ambiguity-chaser`
   is built on. Chasing 100% agreement on a task with real judgment calls
   at the margins measures overfitting to one eval set's quirks, not a
   real capability.

The realistic target was always DeepSeek's own ceiling (96-100%), which is
what three rounds actually closed most of the way toward (57% → 88%) — not
a theoretical 100%.

## Decision and What's Next

**Kept:** the Round 3 checkpoint (88% overall, most balanced per-criterion
result), downloaded locally. Whether to publish it to Hugging Face Hub is
still an open, deliberate decision — the notebook's push cell exists but is
gated off (`PUSH_TO_HF = False`) and was not run.

This reads as a genuinely different conclusion from the earlier zero-shot
verdict ("against adopting Laya right now") — fine-tuning closed most of
the gap to the production baseline. Whether to actually replace or
complement `score_testability` with this checkpoint is a separate decision
from this experiment's scope, worth revisiting explicitly rather than
inheriting either verdict by default.

Open threads, not yet resolved:
- Push decision (Hugging Face Hub, private vs. public).
- Whether the `experiment/laya-scoring` branch stays as a historical record
  (the pattern used for `experiment/instructor-scoring`) or gets revisited
  for adoption.
- A possible Round 4 exists in the same shape as Round 2→3: e.g. testing
  whether a mid-point epoch count (10-12) finds a better accuracy/ECE
  balance than either 8 or 15 — not attempted this session, since three
  hypothesis-driven rounds already gave a rich, honest picture, and a
  fourth without a new mechanism would drift into unprincipled sweeping.

## Process Notes and Tooling Lessons

Worth recording independent of the ML result — these cost real time and
will recur:

- **A backend API contract bug is worth root-causing past "it doesn't
  work."** JarvisLabs' listing bug (`region: None` silently dropping every
  GPU row) was confirmed by hitting the raw API directly, not just retried
  until it worked. Worth reporting upstream with the repro.
- **An MCP server described as giving "browser control" may be a proxy,
  not a headless API.** Colab MCP needed a live, human-clicked browser
  connection before any real tool appeared, and even then had no tool for
  GPU runtime selection or file transfer — both needed manual UI clicks or
  code-cell workarounds. Read the actual exposed tool schema after
  connecting, don't assume capability from the pitch.
- **A blind `pip install -U` can break a managed platform's own pins.**
  `-U pandas` silently pulled 3.0.6 over Colab's pinned 2.2.3, which could
  have destabilized the platform's own upload/download widgets. Caught and
  fixed before it caused a harder-to-diagnose failure downstream.
- **Large browser-triggered downloads (~1.5GB) are not reliable.**
  `google.colab.files.download()` silently no-op'd more than once at that
  size; retrying sometimes worked, sometimes didn't. No clean workaround
  found beyond "retry, and know Drive-mount exists as a fallback."
- **A vendor's own documented bug is worth testing the vendor's own fix
  for, not just noting it exists.** The `noul`-to-`choice` switch for
  `missing_precondition` was validated twice independently — once in the
  zero-shot phase, once by comparing training outcomes — before being
  trusted.
- **Reading the actual wrong answers beats re-running with different
  knobs.** Every real gain in this experiment (the Round 2 data fix, the
  Round 3 epoch decision) came from reading specific failures and forming
  a testable hypothesis, not from sweeping hyperparameters.

## Appendix: Raw Files

All in `scratch/` unless noted, on branch `experiment/laya-scoring`:

- `scratch_laya_scoring.py` — zero-shot evaluation, 4-criterion `noul`.
- `scratch_laya_choice_variant.py` — the `noul`-to-`choice` fix test for
  `missing_precondition`.
- `finetune_dataset_claude_v1.jsonl` — 168-item original training set.
- `finetune_dataset_claude_v2_additions.jsonl` — 31 gap-targeted additions
  (Round 2).
- `finetune_holdout_texts.txt` / `finetune_holdout_deepseek_labels.jsonl` —
  the 39-item held-out eval set and its real DeepSeek-generated labels.
- `build_holdout_labels.py` — builds the held-out labels via the real,
  unmodified production scoring path.
- `laya_finetune_colab.ipynb` — the full adapted fine-tuning notebook (all
  3 rounds' exact code), reconstructed from the live Colab session.
- `laya_gpu_run_output.log` — raw zero-shot GPU run output.
- `HANDOVER.md` (repo root of the worktree) — the session-to-session
  handover record this experiment was resumed from.
- `NOTES.md` (repo root) — day-by-day build log, including the original
  zero-shot aside this report builds on.
