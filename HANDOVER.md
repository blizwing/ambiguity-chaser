# Handover — Laya fine-tuning R&D (updated 26 Sep 2026)

Written for a fresh Claude Code session with zero memory of the conversation
that produced this. **Everything needed to resume is below — do this:**

1. **Google Colab MCP is already installed, registered, and confirmed
   connected** (done 26 Sep 2026, in a separate Claude Code session running
   in the main `ambiguity-chaser` worktree — see "Colab MCP setup" below for
   exactly what was done and verified). You do not need to ask the user to
   connect anything. It's registered at **user scope** (not project scope —
   deliberate, see CLAUDE.md's "Public-repo precautions extend to
   third-party tools/services" bullet), so it should simply be present in
   this fresh session without any extra setup.
2. Run `ToolSearch` for `colab` to load its real schema. Read what it
   actually exposes **before doing anything else** — do not assume
   capabilities you haven't confirmed. Important, per "Colab MCP setup"
   below: this server is a **browser proxy, not a headless API**. The real
   notebook-editing tools (GPU runtime selection, file upload, cell
   execution) only get exposed dynamically *after* a live browser
   connection, made via an injected `open_colab_browser_connection` tool
   that opens an actual Colab tab and waits up to 60s for the user to
   connect it. **That live connection has not happened yet** — expect to
   need Pratham to click through it with you before you can confirm any of
   the capabilities step 2 above is asking about.
3. Then jump straight to **"Next steps"** at the bottom. No research, no
   re-deriving prior findings — this file already contains everything that
   was learned. Do not re-litigate a decision recorded here without flagging
   it to Pratham first.

This file replaces an earlier version of itself that contained two claims
which turned out to be **wrong** — both corrected below, flagged so nobody
re-trusts old git history without re-checking:
- ~~"PAUSED mid-run, no results yet"~~ — wrong. The evaluation run described
  below actually completed, twice (once on CPU, once on GPU), with real,
  consistent results.
- ~~"no discrete GPU"~~ — wrong. This machine has an NVIDIA RTX 4050 Laptop
  GPU, 6GB VRAM.

## What this is

R&D spike evaluating whether **Laya** (`convaiinnovations/laya`, Apache 2.0,
self-hosted, open-weight, 421M params, ModernBERT-large backbone) can
replace or complement the DeepSeek-based `score_testability` node in
`graph.py`. Same shape of experiment as the completed **Jev** aside
(NOTES.md, parked) and the **Instructor** experiment (branch
`experiment/instructor-scoring`, not merged).

**Current status: zero-shot evaluation is done and conclusive. The project
has moved on to evaluating whether *fine-tuning* Laya closes the gap.
Training data for that fine-tune is built. The fine-tuning run itself has
NOT happened yet — that's what this session (with Colab) is for.**

## Where things are

- **Location:** a separate git worktree, sibling to the main repo, at
  `<local-path>/ambiguity-chaser-laya` (main repo is at the same path
  without `-laya`).
- **Branch:** `experiment/laya-scoring`, rebased onto current `main`
  (was originally created off an older commit; rebased 25 Sep 2026 to pick
  up the interrupt/resume work). Not merged, not intended to be merged
  casually — same disposition pattern as `experiment/instructor-scoring`.
- **Venv:** dedicated `.venv` inside this worktree (not the shared one in
  the main repo). Has both a CPU and, later, a CUDA build of `torch`
  installed at different points this session — **currently CUDA**
  (`torch==2.14.0+cu130`, matching this machine's RTX 4050 and driver CUDA
  13.3). `laya==0.3.20`, `tiktoken`, `psutil` also installed here.
- **`.env`:** copied from the main worktree (untracked, gitignored) so the
  real DeepSeek scorer could be called for a real side-by-side comparison
  and to label the held-out validation set (see below).
- **requirements.txt:** `laya` appended (mirrors the Instructor experiment's
  pinning pattern — may get reverted if Laya isn't adopted).
- **Uncommitted files currently in this worktree** (per CLAUDE.md, Claude
  never commits here — these are all waiting for Pratham to review/commit):
  - `scratch/scratch_laya_scoring.py` (modified — `Router(device="cuda")`)
  - `scratch/scratch_laya_choice_variant.py` (new)
  - `scratch/build_holdout_labels.py` (new)
  - `scratch/finetune_dataset_claude_v1.jsonl` (new — **the training set**)
  - `scratch/finetune_holdout_texts.txt` (new)
  - `scratch/finetune_holdout_deepseek_labels.jsonl` (new — **the held-out eval set**)
  - `scratch/laya_gpu_run_output.log` (new — raw log from the GPU eval run)
  - This `HANDOVER.md` itself (modified)

## What's already been found — do not re-derive any of this

### 1. Zero-shot accuracy: real, run twice, consistent

`scratch/scratch_laya_scoring.py` — 8 hand-labeled requirements, 4 criteria
(`has_measurable_condition`, `has_vague_qualitative_language`,
`has_ambiguous_scope`, `missing_precondition`), Laya's `noul` questions
worded verbatim from `prompts/testability_score_v1.txt` (fairness
constraint — don't reword them), same `compute_testability_score()` scoring
both arms, `>= 0.5` noul→bool threshold (Laya's own internal convention).

Run once on CPU, once on GPU (after installing a CUDA torch build) — same
shape of result both times:

| | CPU run | GPU run |
|---|---|---|
| Laya overall accuracy | 17/28 (61%) | 16/28 (57%) |
| DeepSeek baseline accuracy | 27/28 (96%) | 28/28 (100%) |
| `missing_precondition` accuracy | worst criterion both times | 2/7 (29%) |
| confidently-wrong answers (conf ≥0.8) | all 4 on `missing_precondition` | all 4 on `missing_precondition` |
| determinism | 32/32 pairs exactly repeatable | 32/32 pairs exactly repeatable |
| latency, Laya | 1.44s/call (CPU) | **0.13s/call (GPU, ~11x faster)** |
| latency, DeepSeek baseline | 3.01s/call | 3.00s/call (unchanged, API-bound) |

**`missing_precondition` is consistently the worst criterion, and the only
one with confidently-wrong answers.** GPU changes latency, not accuracy —
same weights, same zero-shot task.

### 2. Root cause investigated, not assumed — two contributing factors found

**(a) fp32 confirmed from source, not guessed.** `laya/agent.py` builds the
encoder with no `torch_dtype` override → upcasts the fp16-stored checkpoint
to full fp32 on CPU (`self.dtype = torch.float32`, `amp_enabled=False`
unless `LAYA_CPU_AMP=bf16`, which we never set). No quantization path exists
anywhere in the library — confirmed by reading the source, not the pip
warning text. So the accuracy gap is **not** a precision/setup problem.

**(b) `noul` has a documented label-anchoring bug, and we tested the
vendor's own suggested fix.** The model's HF README ("Honest Limits"
section) says: *"`noul` can follow its option labels instead of the state,
most strongly on this English checkpoint... ask the same question as a
two-option `choice` instead."* `missing_precondition` is phrased as a
negation ("does the requirement *fail* to state...") — exactly the shape
where this would bite. Tested in `scratch/scratch_laya_choice_variant.py`:
switching just that one criterion from `noul` to `choice` (keeping the
other 3 as `noul`, unchanged) moved `missing_precondition` from **2/7 (29%)
→ 3/7 (43%)**, and eliminated all confidently-wrong answers (max confidence
dropped from 0.90 to 0.78). **Real improvement, but still far below the
baseline's 100%** — the bug was real but isn't the whole story.

One self-caught bug worth knowing about if you touch `choice`-type answers:
`choice` responses carry two different confidence fields — `confidence`
(Shannon-entropy based, `common.py` explicitly says "not calibrated") and
`answer_confidence` (`max(p)`, the one temperature-scaling/ECE actually
measures). They're only equal for `noul`. Use `answer_confidence` for
anything you compare against a threshold.

**(c) The real limiting factor, per the vendor's own model card:** base
Laya checkpoints are described as *"near chance on typed-decisions
zero-shot... Laya is a fast base to specialise, not a zero-shot decision
engine."* Their own benchmark: the same checkpoint scores **0.362 zero-shot
→ 0.766 after fine-tuning** on their own 2,000-decision typed-decisions
benchmark. Our task (judging structural/compositional properties of a
sentence) is much closer to their "decision" benchmark than to simple topic
classification (where the same zero-shot checkpoint does fine: 0.950 on AG
News). **This is why the project moved to fine-tuning instead of just
prompt-tweaking.**

### 3. Fine-tuning resource research — real vendor numbers, not estimated

Two real reference points, pulled directly from `github.com/NandhaKishorM/laya`:

| | GPU(s) | Dataset | Epochs | Time |
|---|---|---|---|---|
| Vendor's typed-decisions benchmark | 2×T4 (32GB total) | ~30k questions | 4 | 4–5 hours |
| Vendor's browser-agent worked example (**same 421M checkpoint we use**) | 1×RTX 4070 Ti SUPER, 16GB, no grad checkpointing | ~14k examples | 4 | **~2 hours** |

**Our own hardware (RTX 4050, 6GB) almost certainly cannot fit a full
fine-tune.** Real arithmetic: 421M params × 4 bytes (fp32) × 4 (weights +
gradients + Adam's 2 optimizer moments) ≈ **6.7GB, before any activations**
— already exceeds our 6GB card, and the vendor's own successful single-GPU
run needed 16GB *without* gradient checkpointing. This is why the plan
moved to renting external compute.

### 4. JarvisLabs — tried, found a real bug + zero live inventory, not a plan B right now

Auth is fine (`jl status`). But `jl gpus --json` / `jl resources --json`
return an **empty GPU list**. Root-caused by hitting the raw backend API
directly (bypassing the CLI) against all three regional endpoints:

```
Noida:    {'gpu_type': 'RTX5000', 'vram': '16', 'num_free_devices': 0, 'region': None}
Chennai:  {'gpu_type': 'RTX5000', 'vram': '16', 'num_free_devices': 0, 'region': None}
Europe:   {'gpu_type': 'RTX5000', 'vram': '16', 'num_free_devices': 0, 'region': None}
```

The installed CLI (`jl` 0.2.14, `jarvislabs/client.py`) filters GPU rows
with `gpu.region in REGION_URLS`. The backend no longer sets `region` on
GPU rows (`None`), so every row gets silently dropped — a real
client/backend API contract mismatch, not user error. **Separately and
regardless of that bug: real live inventory is 0 free devices of the only
listed GPU type, in all three regions, as of 25 Sep 2026.** Worth reporting
to JarvisLabs support (repro above) and rechecking `jl gpus` periodically,
but **not currently usable** — this is why the user proposed Colab instead.

**Confirmed a second, independent way (26 Sep 2026) — don't re-attempt this
check, it's conclusive.** Registered an SSH key (`jl ssh-key add`, needed
for the VM path regardless) and tried actually creating an instance —
both `--vm` and plain GPU container, across all three regions (default,
`--region IN1`, `--region EU1`). All six attempts failed straight from the
**create endpoint itself** (not the buggy listing):

```
VM,        Noida (default): "No pricing for RTX5000 in india-noida-01"
VM,        IN1:              "RTX5000 is not available in IN1."
VM,        EU1:               "RTX5000 is not available in EU1."
Container, Noida (default): "No pricing for RTX5000 in india-noida-01"
Container, IN1:              "RTX5000 is not available in IN1."
Container, EU1:               "RTX5000 is not available in EU1."
```

No instance was ever provisioned, no cost incurred. This rules out "maybe
the listing bug is hiding real capacity" — the create endpoint itself
confirms zero usable GPU capacity, VM or container, in any region, for this
account. The SSH key is registered or next time capacity exists, but there
is currently nothing to launch it on. **Don't re-run this check — it's
settled. Move straight to Colab.**

### 5. Training data — built, not yet used

Decision made explicitly with the user: **Claude authors the training
dataset directly** (not via DeepSeek — token cost was measured and is
trivial either way, ~55 tokens/item; the real constraint is quality control,
not tokens). **DeepSeek is used only to label a separate held-out validation
slice**, so the fine-tuned model's real test is agreement with the actual
production judge, not with Claude's own labels (train and eval ground truth
are deliberately from different sources — don't merge these files).

- **`scratch/finetune_dataset_claude_v1.jsonl`** — 168 items, Claude-authored
  text AND labels. Schema: `{"text": ..., "has_measurable_condition": bool,
  "has_vague_qualitative_language": bool, "has_ambiguous_scope": bool,
  "missing_precondition": bool}`. 11 of 16 possible label combinations
  represented (skewed toward the two dominant archetypes — "clear" 62/168,
  "fully vague" 34/168 — same pattern as the original 8-item eval set, plus
  genuine mixed cases). Spans ~15 domains (e-commerce, healthcare, IoT,
  support/CRM, DevOps, social/content moderation, gaming, logistics,
  edtech, gov, fintech, HR, video conferencing, docs/collab, mobile, API
  platforms, security, SaaS billing).
- **`scratch/finetune_holdout_texts.txt`** — 40 new, non-overlapping
  requirement texts, Claude-authored, text only.
- **`scratch/finetune_holdout_deepseek_labels.jsonl`** — 39 rows (1 of 40
  came back `invalid_json` from DeepSeek — a real, measured ~2.5% failure
  rate at this scale, worth budgeting for, not assuming away). Built by
  `scratch/build_holdout_labels.py`, which runs each held-out text through
  the real, unmodified `call_deepseek_json` + `validate_response` path
  against `testability_score_v1.txt`. Schema matches the training file plus
  a `reasoning` string from DeepSeek. **This is the file to evaluate the
  fine-tuned checkpoint against — not the training labels.**

**Open decision, not yet made — flag to Pratham, don't decide silently:**
should the fine-tuning question set use `choice` for `missing_precondition`
(per the tested fix above) instead of `noul`? The zero-shot eval kept a
strict "verbatim `noul` wording" fairness constraint; fine-tuning is a
different context (the model gets to learn from labeled examples either
way), so this tradeoff is worth re-opening explicitly rather than silently
inheriting the zero-shot methodology's constraint or silently switching
without discussion.

## What Laya actually is (still true, unchanged from original research)

- Package: `laya` (`.venv/Lib/site-packages/laya/`). Entry point: `from
  laya import Router`.
- **Three checkpoints**, auto-routed by script/language: `english` (421M,
  ModernBERT-large, 512 tokens — what we use), `multilingual` (322M,
  mmBERT-base), `typed-decisions` (421M, fine-tuned on 4 unrelated
  synthetic workflows — not relevant to us).
- **Three question primitives:** `choice`, `score` (ordinal), `noul`
  (boolean, `P(true)` + calibrated `answer_confidence`).
- **Low-level API:** `router.predict(state, questions_dict)` — one forward
  pass answers every question at once. This is what our scripts use.
- **Higher-level `laya.structured` schema path exists but is deliberately
  unused** — rejects free-text fields (our `TestabilityScore.reasoning`
  wouldn't fit) and derives weaker auto-generated question wording than our
  hand-worded ones. Don't switch to it without discussing the tradeoff.
- **Fine-tuning is RLCD** (Reinforcement Learning for Calibrated Decisions):
  policy reports a distribution, exploration adds zero-mean Gaussian noise
  to logits, reward is a strictly-proper scoring rule (log + spherical +
  ranked-probability for ordinal), REINFORCE with a group-mean baseline
  (GRPO-style). Vendor's fine-tuning notebook does the whole loop: build
  dataset → train → fit calibration temperatures → evaluate → push to hub.
  Reference: `github.com/NandhaKishorM/laya/blob/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb`
  and the `## Fine-Tuning` section of that repo's README.

## System / compute facts (confirmed via actual queries, not estimated)

- CPU: Intel i5-1135G7, 4 cores / 8 threads.
- **GPU: NVIDIA GeForce RTX 4050 Laptop GPU, 6GB VRAM**, driver reports CUDA
  UMD 13.3. `torch==2.14.0+cu130` installed and confirmed working
  (`torch.cuda.is_available() == True`).
- RAM: 32.47GB total, 17.0GB free at last check (healthier than an earlier
  4.3GB reading — recheck before a heavy run regardless).
- OS: Windows 11. HF cache-symlink optimization disabled (Developer Mode
  not on) — harmless, just slightly more disk use.
- Real measured peak RSS for a full fp32 inference forward pass (not
  training): steady-state ~2.08GB, transient peak ~2.64GB. **Do not confuse
  this with training memory** — training needs weights+gradients+optimizer
  state resident simultaneously, a different and much larger number (see
  point 3 above, ~6.7GB minimum before activations).

## Colab MCP setup (done 26 Sep 2026 — new since the previous version of this file)

JarvisLabs was a confirmed dead end (section 4 above), so the user proposed
Colab. Set up and verified in a separate Claude Code session (main
`ambiguity-chaser` worktree, not this one — no worktree/branch swap was
done; see "Worktree note" below for why).

- **Registered:**
  `claude mcp add colab-mcp -s user -- uvx git+https://github.com/googlecolab/colab-mcp`
  — **user scope**, deliberately, not `project`. `project` scope writes to
  a committed `.mcp.json`, which would publish the server config to this
  public repo — now a standing rule, see CLAUDE.md's "Public-repo
  precautions extend to third-party tools/services" bullet (added same
  day).
- **Verified real, not a guessed/hallucinated URL:** confirmed via
  `gh api repos/googlecolab/colab-mcp` (real repo under the `googlecolab`
  GitHub org, Apache-2.0, 1000+ stars, pushed as recently as Jun 2026), and
  by reading its actual `README.md` and `src/colab_mcp/session.py` source —
  not just trusting a web search summary.
- **Confirmed connecting:** `claude mcp list` → `colab-mcp: ... - ✔
  Connected`. The first check timed out at 30s — that was just `uvx`
  cloning + building the environment on first run, not a real failure. A
  manual `uvx git+https://github.com/googlecolab/colab-mcp` run (done by
  Pratham directly — Claude Code's auto-mode classifier blocks Claude
  itself from executing freshly-downloaded external code) confirmed it
  starts cleanly as a FastMCP stdio server. A second `claude mcp list`
  check with the `uv` cache warm came back Connected.
- **Architecture — important, don't assume more than this:** it's a
  **proxy**, not a headless/batch API. `uvx` starts a local websocket
  bridge; nothing useful happens until a tool call to the
  middleware-injected `open_colab_browser_connection` opens an actual Colab
  tab in the user's browser and waits (60s timeout) for it to connect. Only
  *after* that live connection does the browser session dynamically expose
  the real notebook-editing tools via `notifications/tools/list_changed` —
  they are **not** hardcoded in the server, and were **not enumerated** in
  this setup session (no live browser connection was made yet). So: GPU
  runtime selection, the file-upload mechanism, and cell-execution
  capability are all still **unconfirmed** — that's the first thing to
  check once `ToolSearch` shows the tools are loaded, per step 2 above.
- **Not yet done:** the actual live browser connection (clicking through
  `open_colab_browser_connection` with Pratham watching) hasn't happened.
  The registration-only session ended before that step specifically so a
  fresh session with the tool already loaded could pick it up cleanly.
- **Worktree note:** Pratham asked about moving this worktree to a
  different branch/location so the laya work would be visible in the main
  session's folder directly. Decided **against** any git/filesystem change
  — git can't check out the same branch in two worktrees at once, and the
  folder-swap alternative would've broken both worktrees' `.venv`s (which
  have absolute paths baked in). **No change was made**: this worktree is
  still at its original path (`ambiguity-chaser-laya`), still on
  `experiment/laya-scoring`. The fresh session should just operate on it
  directly by path, same as always.

## Next steps — do these in order

1. **Confirm the Colab MCP tools are loaded** (`ToolSearch` for `colab`) and
   then make the **live browser connection** (call
   `open_colab_browser_connection`, walk through it with Pratham — it opens
   a Colab tab and waits up to 60s). Only after that connection succeeds
   will the real tools appear. Read what they actually expose before
   assuming anything — specifically check: can it request a GPU runtime
   (T4) explicitly, not just default to CPU? Can it upload local files or
   does it need Drive/another transfer path? Can it run cells and read
   their output back into this session?
2. **Request/select a T4 GPU runtime explicitly** — don't assume the
   default runtime type. T4 has 16GB VRAM, matching the vendor's own proven
   single-GPU fine-tune scale (~2 hours for this exact 421M checkpoint).
3. **Pull the vendor's fine-tuning notebook as a reference**
   (`notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb` in
   `github.com/NandhaKishorM/laya`) and adapt it to our schema — our 4
   `noul` (or `choice`, per the open decision above) boolean criteria, not
   their department/urgency/choice/score mix. Reuse their RLCD training
   loop, calibration-temperature-fitting step, and held-out eval step
   rather than reimplementing from scratch.
4. **Upload our 3 data files** to the Colab environment:
   `scratch/finetune_dataset_claude_v1.jsonl` (train, 168 items),
   `scratch/finetune_holdout_texts.txt` + `finetune_holdout_deepseek_labels.jsonl`
   (held-out eval, 39 items — labels from real DeepSeek, not Claude).
5. **Run the fine-tune.** Expect roughly ~2 hours based on the vendor's own
   number for this checkpoint at this rough dataset scale — actually monitor
   it, don't assume that figure transfers exactly to our smaller dataset
   without checking.
6. **Fit calibration temperatures** per the notebook's own methodology (one
   temperature per question type — the vendor's README warns the base
   checkpoint ships over-confident, ECE 0.466 → 0.081 after fitting).
7. **Evaluate against `finetune_holdout_deepseek_labels.jsonl`** — this is
   the real "did it work" check, since those labels come from the actual
   production judge, not from the same source as the training data.
8. **Download the resulting checkpoint** back. Decide whether to push to HF
   Hub or keep local — Pratham's call.
9. **Write up the outcome in NOTES.md**, same pattern as the Jev and
   Instructor asides (goal / done / found / decision / branch disposition).
   Claude drafts, Pratham reviews and validates before committing.
10. **Per CLAUDE.md: Claude never runs `git add`/`git commit`/`git push` in
    this repo.** Give Pratham the exact commands to run himself — plain
    message, no co-author line.

## Things NOT to redo

- Don't re-run the zero-shot eval from scratch "to be sure" — it's been run
  twice (CPU and GPU) with consistent results. Trust section 1 above.
- Don't re-debug JarvisLabs — the bug is real, reproduced against all three
  regional backends directly, and the fix isn't on our end.
- Don't re-derive the fp32/quantization/`noul`-bug investigation — it's
  done, sourced, and the conclusion (architecture + a documented primitive
  bug, not precision) is solid.
- Don't silently decide the `noul`-vs-`choice` question for
  `missing_precondition` in the fine-tuning schema — it's flagged as open
  above specifically so it gets a conscious decision, not a default.
- Don't re-verify the `colab-mcp` registration or re-litigate `user` vs.
  `project` scope — it's done, verified against the real GitHub repo, and
  the reasoning is recorded above. Do go ahead and make the live browser
  connection, though — that part is genuinely not done yet.
- Don't re-attempt the worktree branch/folder swap Pratham asked about —
  already decided against, reasoning recorded above.
