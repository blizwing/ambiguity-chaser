# Notes

Day-by-day build log for Ambiguity Chaser (Phase 2). Same format as
`eval-harness/NOTES.md`: one dated entry per build day, goal, what got
built, what was found, why it matters going forward, checkpoint met, raw
files touched.

---

## Week 6 — Env setup, live smoke test, DeepSeek model-change research (14 Sep 2026)

**Goal:** local dev environment ready and a live API call confirmed
working, ahead of Saturday's SESSION 3 (`/advanced-learn` LangGraph
fundamentals). No day-level ROADMAP.md breakdown exists yet for Week 6 —
intentional, per the roadmap's own "daily detail comes when you get
there" note — so this is prep, not a scoped DONE WHEN.

**Done:**
- `.venv` already had every package from `requirements.txt` installed
  (`anthropic`, `openai`, `langgraph`, `langchain-core`, `pydantic`,
  `pytest`, `python-dotenv`, `pyyaml`); confirmed clean imports including
  `from langgraph.graph import StateGraph`, Python 3.12.10.
- Confirmed provider: this repo runs on the **DeepSeek API**, not
  Anthropic/OpenAI directly, for cost reasons — `openai` SDK is used as
  the client pointed at DeepSeek's OpenAI-compatible endpoint
  (`base_url="https://api.deepseek.com"`). `.env.example` already had the
  right key placeholder (`DEEPSEEK_API_KEY`).
- Created local `.env` (gitignored, never committed) and ran a live
  smoke-test call — round-tripped correctly (`"pong"` back,
  prompt_tokens=12, completion_tokens=2).

**Found:** the smoke test requested `model="deepseek-chat"` but the
response echoed back `model: deepseek-flash` — not a bug. Researched from
DeepSeek's own changelog (api-docs.deepseek.com/updates/), not just
aggregator summaries:
- `deepseek-chat` / `deepseek-reasoner` were deprecated 24 Jul 2026 —
  still accepted, but silently routed to V4.1-Flash instead of the model
  actually named.
- DeepSeek-V4.1-Flash shipped 10 Sep 2026 under canonical model ID
  `deepseek-flash`. `deepseek-v4-flash` still works as a temporary alias
  to the same model.
- Pricing changed with that release: off-peak $0.15/$0.60 input/output
  per 1M tokens (cache-miss), peak $0.30/$1.20. Peak window: 01:00–04:00
  and 06:00–10:00 UTC, Mon–Fri; everything else off-peak.
- **Checked `eval-harness` first, before researching externally:** this
  is the exact incident already caught and diagnosed there on Wed 10 Sep
  2026 (`eval-harness/NOTES.md`, "Incident — `deepseek-v4-flash` alias
  repointed, judge pass rate collapsed") — a judge pass-rate collapse
  traced to the same alias silently changing model behavior with zero
  code changes on their side. `eval-harness/Day3_llm_client.py` already
  has corrected pricing constants and peak/off-peak logic (fixed 11 Sep
  2026 follow-up) that match what's published today — i.e. still
  current, not stale.
- **One discrepancy left open, not resolved:** `eval-harness`'s notes and
  several aggregator sites expected `deepseek-v4-pro` to also start
  rerouting to V4.1-Flash on 14 Sep 2026 (today). DeepSeek's own
  changelog instead says v4-pro continues as a distinct model
  (`DeepSeek-V4-Pro-0813`) with unchanged billing post-14 Sep. Doesn't
  block current work — neither repo uses v4-pro — but not treated as
  settled either way.

**Why this matters going forward:** confirms `eval-harness/Day3_llm_client.py`
is portable as-is rather than needing a fix first. Decided to defer
porting it into this repo until Week 7 ("Port Phase 1 prompt into a
single-node graph") rather than doing it opportunistically today, per
ROADMAP.md's own red flag against reaching back into `eval-harness` to
redesign something already decided there. New code going forward should
request `deepseek-flash` explicitly rather than the deprecated
`deepseek-chat` alias, per this repo's carried-over P1 finding that
config must always be explicit, never inherited/assumed.

**Checkpoint met:** live DeepSeek API call succeeded end-to-end with a
real key; no formal DONE WHEN to check against since Week 6 has no
day-level plan yet — this closes out pre-Saturday prep.

**Raw files:** `.env` (created, gitignored, not committed), scratchpad
`smoke_test.py` (temporary, not part of the repo).

---

## Week 7 — LangGraph fundamentals, hands-on (21 Sep 2026)

**Goal:** learn LangGraph's node/edge/state mechanics by building, not by
reading — SESSION 3 (`/advanced-learn` LangGraph fundamentals, scheduled
Sat 19 Sep) was deliberately skipped in favor of this. Explicit call: go
hands-on first. This is prep before Week 7's actual task (port the Phase 1
prompt into a real single-node graph), not that task itself.

**Done:**
- Confirmed `.venv` already had `langgraph==1.2.11` / `langchain-core==1.6.3`
  installed from the 14 Sep prep — no new installs needed today.
- Built `scratch/scratch_graph.py`: a `State` (`TypedDict`, one field
  `text: str`), one node (`shout` — uppercases `text`), wired
  `START -> shout -> END` explicitly, compiled, invoked with
  `{"text": "hello"}` -> `{'text': 'HELLO'}`.
- Extended to a second node: added `exclaim` (appends `"!"`), rewired the
  edges to `START -> shout -> exclaim -> END`. Ran end-to-end ->
  `{'text': 'HELLO!'}`, print statements inside each node confirmed
  execution order is driven by the declared edges, not by which function
  happened to be defined or called first in the file.
- Clarified (own question, worth recording): LangGraph's `State` type is
  not enforced at runtime when declared as `TypedDict` — it's editor/type-
  checker-only typing. A node can return any dict shape and LangGraph will
  merge it into the running state key-by-key with zero validation. Flagged
  Pydantic `BaseModel` as the enforced alternative to switch to once past
  toy examples — relevant here specifically because this project's whole
  premise (score -> emit spec or ask, never fabricate) can't tolerate
  silent state drift the way a throwaway script could.

**Found:**
- Real bug, fixed hands-on: `from langgraph import graph` imported the
  *module* and bound it to the name `graph`; the next line,
  `graph.StateGraph(State)`, created a `StateGraph` instance but never
  assigned it to anything, so every later `graph.add_node(...)` /
  `add_edge(...)` call was hitting the module, not an instance —
  `AttributeError: module 'langgraph.graph' has no attribute 'add_node'`.
  Fixed by dropping the module import and assigning
  `graph = StateGraph(State)`.
- Pylance briefly reported stale `"graph" is not defined` diagnostics
  right after that same-session edit, before it re-scanned the saved
  file — not a real error; running the script directly gave correct
  output before the warning cleared. Worth remembering next time an edit
  and a lingering red squiggle disagree.

**Why this matters going forward:** the three fundamentals exercised here
— state as a shared dict, nodes as functions registered by name, edges as
declared control flow independent of a function's call site in the
source — are exactly what Week 8's conditional branching (score -> "emit
spec" or "ask questions") and Week 9's interrupt/resume build on. Neither
of those is a plain Python `if/else`; both lean on `add_edge`/`add_node`
the same way this toy graph did.

**Checkpoint met:** two-node graph runs end-to-end with edge-driven (not
call-order-driven) execution confirmed via printed intermediate state. No
formal Week 7 day-level DONE WHEN existed yet for this step — it's the
hands-on-fundamentals prep before porting the real Phase 1 prompt into a
node, planned for later today.

**Raw files:** `scratch/scratch_graph.py` (committed in two steps: single-
node version, then the two-node version).

---

## Week 7 — Port Phase 1 prompt into a single-node graph (21 Sep 2026)

**Goal:** the actual ROADMAP.md Week 7 task — replace the toy `shout`/
`exclaim` workers with one real node that calls DeepSeek using
eval-harness's Phase 1 test-case-generation prompt and returns a validated
structured spec.

**Done:**
- Ported three pieces from `eval-harness`, minimal-only (no redesign, per
  ROADMAP's own red flag against reaching back into eval-harness to
  rebuild something already decided there):
  - `llm_client.py` — from `Day1_first_call.py` / `Day4_json_mode.py`.
    Only the OpenAI-schema JSON-mode call path is ported; the
    Anthropic-schema path isn't, since this repo only ever talks to
    DeepSeek via the `openai` SDK (confirmed 14 Sep prep). Requests
    `deepseek-flash` explicitly, not the deprecated `deepseek-chat` alias.
  - `schemas.py` — just `TestCase` and `validate_response`, not
    eval-harness's full model zoo.
  - `prompts/testcase_v1.txt` — verbatim copy of
    `Day7_prompt_file/prompt_testcase_v1.txt`.
- Caught mid-build: a fresh file was created at `Progress/Day1_Init/Day1.py`
  — day-numbered, exactly the naming pattern CLAUDE.md says this repo
  deliberately avoids. Moved to `graph.py` at repo root before writing any
  real code into it.
- Built `graph.py`: `GraphState` (Pydantic `BaseModel`, not `TypedDict` —
  deliberate choice, since this project can't tolerate silent state drift
  the way a throwaway script could) with `requirement`, `status`,
  `test_case` fields; one node, `generate_test_case`, that formats the
  prompt, calls `call_deepseek_json`, and runs the result through
  `validate_response`; wired `START -> generate_test_case -> END`.
- Ran against `"The system must lock a user account after 5 failed login
  attempts."` — valid `TestCase` came back end-to-end, specific and
  verifiable (`expected_result`: "After the fifth failed login attempt,
  the user account is locked.", `priority: high`). Week 7's DONE WHEN met.

**Found — proved the actual gap this project exists to close, on purpose:**
ran the same graph 5x against a deliberately vague requirement
(`"The system should be fast."`) before stopping for the day, to see what
happens without any ambiguity gate:
- 3/5 calls: valid, and the prompt's own ambiguity rule worked correctly —
  each one noted the missing speed threshold inside `expected_result`
  (e.g. "Pass/fail cannot be determined because requirement provides no
  measurable speed threshold") instead of inventing a fake number.
- 1/5: `invalid_json` — `stop_reason: length`, `output_tokens: 1024`,
  response truncated mid-field. Root cause: `MAX_TOKENS = 1024`, ported
  unchanged from eval-harness's `Day1_first_call.py`, which sized it for a
  one-line haiku response, not a multi-field JSON object with a written
  ambiguity explanation. **Fixed same day** — bumped to `MAX_TOKENS = 2048`
  in `llm_client.py` and reran the same 5-call test: 5/5 valid, all
  `stop_reason: stop`; one of the five used 1241 output tokens, confirming
  this wasn't a one-off — it would have truncated under the old cap too.
- 1/5 (before the fix): `invalid` — well-formed JSON, but the model
  silently omitted the required `"priority"` field. Not a bug:
  `validate_response`/Pydantic caught it correctly, exactly the
  grader-integrity discipline CLAUDE.md calls out as carrying over from
  P1's `ScoreIntegrityError`.
- Live confirmation of the P1 "non-determinism at temperature=0" finding:
  five calls to the identical prompt produced meaningfully different
  completions (three clean passes, one truncation, one schema miss) —
  not exact-match-diffable, exactly as CLAUDE.md already warned.

**Why this matters going forward:** `graph.py` as it stands has zero
ambiguity gating — it emits a `TestCase` for any requirement that happens
to produce valid, schema-conformant JSON, vague or not. Today's 5-call
test made that gap concrete rather than theoretical, and incidentally
surfaced a real config bug (undersized `MAX_TOKENS`) that would have kept
causing intermittent `invalid_json` failures indistinguishable from a real
model problem if left at the ported default. Week 8 is the fix for the
gating gap: score testability first, then conditionally route to either
this node or an as-yet-unwritten "ask clarifying questions" node — the
actual differentiator this project exists to build, not yet started.

**Checkpoint met:** Week 7 ROADMAP.md task complete — single-node graph
running the ported Phase 1 prompt, producing a validated `TestCase` for a
clear requirement. Deliberately stopped here rather than starting Week 8
in the same session, per today's plan.

**Raw files:** `llm_client.py`, `schemas.py`, `prompts/testcase_v1.txt`,
`graph.py` (all new, not yet committed).

---

## Week 8 — Conditional edges: score testability, then route (22 Sep 2026)

**Goal:** the ROADMAP.md Week 8 task — stop unconditionally generating a
test case for every requirement, vague or not (the gap Week 7 proved
concrete). Score a requirement's testability first, then conditionally
route to either `generate_test_case` or a new "ask clarifying questions"
node, using a real LangGraph conditional edge instead of one fixed path.

**Done:**
- Checked `eval-harness` first, before designing anything new, per
  ROADMAP's red flag against rebuilding something already decided there.
  `JudgeScore` (`eval-harness/schemas.py`) and `judge_v2.txt` looked like a
  candidate but turned out to score the wrong thing: they judge a
  *generated test case's* quality against its requirement, after
  generation — nothing in `eval-harness` scores a raw requirement's
  testability *before* generation. Not a port candidate. Two things were
  still worth reusing as patterns, not code: the rubric shape (independent
  criteria + reasoning, hard criteria vs soft criteria feeding a verdict),
  and `ScoreIntegrityError`'s discipline of not trusting a grader's own
  output blindly.
- Domain call (Pratham's, deduction method): built `TestabilityScore` — 4
  boolean criteria the model reports as facts about the requirement text
  (`has_measurable_condition`, `has_vague_qualitative_language`,
  `has_ambiguous_scope`, `missing_precondition`) plus one-sentence
  reasoning. `compute_testability_score` in `schemas.py` turns those
  booleans into a score in Python, not the model: `has_measurable_condition`
  is a hard gate (fail it, score is 0, nothing else matters — there's
  nothing to test without at least one verifiable condition); each
  remaining soft criterion present costs 15 points off a 100 start. Model
  reports facts, code does the arithmetic — same discipline as
  `eval-harness`'s `JudgeScore`/`ScoreResult` split, and avoids trusting the
  model to self-report a number it might just invent a plausible-looking
  value for.
- Added `ask_clarifying_questions` node + `prompts/clarifying_questions_v1.txt`
  — takes the requirement plus a human-readable summary of which criteria
  failed, asks the model for specific, targeted clarifying questions (no
  proposed answers, no invented example values). Guards against a
  technically-valid-but-empty response (`questions: []`) by treating it as
  invalid rather than trusting it — same grader-integrity discipline as
  above, applied to this repo's own output this time, not `eval-harness`'s.
- Wired a real `add_conditional_edges` in `graph.py`:
  `START -> score_testability -> (generate_test_case | ask_clarifying_questions) -> END`,
  replacing Week 7's single fixed path.
- Tested three cases end-to-end: the Week 7 clear requirement (account
  lockout) scored 100, routed to `generate_test_case`, produced the same
  quality spec as before. The Week 7 vague requirement ("the system should
  be fast") hit the hard gate, scored 0, routed to `ask_clarifying_questions`,
  produced 8 targeted questions instead of any fabricated spec — Week 8's
  actual DONE WHEN. A deliberately-constructed middle-ground requirement
  ("must respond in under 2 seconds in most cases") scored 70 (two soft
  deductions), used to pressure-test the threshold itself.

**Found — two real issues, caught by testing rather than assumed away:**
- **Threshold boundary bug, self-inflicted and caught same session:** first
  set `TESTABILITY_THRESHOLD = 70`, saw the middle-ground case pass through
  to `generate_test_case` despite a genuine ambiguity ("most cases" of
  what?), and decided the gate should be stricter — zero soft failures
  tolerated. Raised to 85, but `route_by_testability` checks
  `score >= TESTABILITY_THRESHOLD`, and one soft failure scores exactly 85
  — `85 >= 85` is `True`, so 85 still let one soft failure through despite
  being described (wrongly, in-session) as "zero tolerance." Caught by
  directly testing the boundary with a synthetic single-soft-failure
  `TestabilityScore`, not by inspection. Fixed by bumping to
  `TESTABILITY_THRESHOLD = 86` (comment left in `schemas.py` explaining why
  86 and not 85) — now only a flawless 100 clears the gate, matching the
  actual intent.
- **Non-determinism shows up in the scoring step itself, not just
  generation:** ran the identical, unchanged clear requirement (account
  lockout) through the full graph 4 more times after fixing the threshold.
  3/4 scored 100 as expected; 1/4 scored 85 — the model itself decided,
  that one run, that the same unchanged text had a soft ambiguity issue it
  hadn't flagged the other three times. This extends the Week 7 finding
  (temperature=0 isn't fully deterministic) one layer earlier than already
  known: it's not just that the generated test case varies run to run, the
  ambiguity judgment feeding the routing decision varies too. Not fixed
  today — left as a known limitation, since it can't be eliminated, only
  mitigated (e.g. a future majority-vote-across-N-calls approach).
- **Left open, not fixed:** when the scorer's own output fails schema
  validation, `score_testability` forces the score to 0 (a defensible
  fail-safe — can't confidently score it, so don't confidently generate a
  spec either) but that failure gets written to `state.status`, which is
  then silently overwritten by whichever node runs next. End result: the
  final output can't distinguish "score is 0 because every criterion
  genuinely failed" from "the scorer's own response was malformed and this
  is a forced default." Arguably fine under CLAUDE.md's own rule not to
  split a status when the caller's handling doesn't differ (both cases
  route to asking a question either way) — but flagged since it would
  block ever measuring how often the scorer itself is unreliable versus how
  often requirements are genuinely bad.

**Why this matters going forward:** Week 8's actual differentiator now
works — a vague requirement gets a question, not a fabricated spec — but
the non-determinism finding means the gate isn't a stable, repeatable
judge yet: the same input can land on either side of the threshold across
runs. That's worth carrying into whatever comes after Week 8, rather than
assuming today's single-call scorer is trustworthy as-is. The
boundary-arithmetic bug is also a good concrete reminder that a threshold
described in English ("zero tolerance") needs to be checked against the
actual comparison operator, not just the number.

**Checkpoint met:** Week 8 ROADMAP.md task complete — conditional edge
actually branches based on a computed score, tested against clear/vague/
middle-ground requirements, threshold tuned and its boundary bug fixed
same session.

**Raw files:** `prompts/testability_score_v1.txt`,
`prompts/clarifying_questions_v1.txt` (new); `schemas.py`, `graph.py`
(modified, not yet committed).

---

## Week 9 — Interrupt/resume mechanics, hands-on (23 Sep 2026)

**Goal:** learn LangGraph's pause/persist/resume mechanics by building, not
by reading — same call as Week 7: go hands-on before Saturday's SESSION 4
(`/advanced-learn` human-in-the-loop interrupts), rather than starting the
real `ask_clarifying_questions` interrupt work cold. No day-level
ROADMAP.md breakdown exists yet for Week 9, so today's DONE WHEN was
scoped in-session rather than pulled from the file: prove a graph can (1)
pause at a node without crashing, (2) have that paused state survive being
picked up by a completely separate process, and (3) resume from that
separate process with a human-supplied answer and finish correctly.

**The mental model (for future-me, re-reading this cold):** it's an online
form that saves your progress. You fill in what you can, hit a question it
can't answer for you, and the site saves everything so far and freezes
there — no crash, just parked. Close the tab (or lose the whole machine),
come back later, log in again: it shows you exactly where you left off,
because that came from its database, not from anything still open in a
browser tab. Answer the question, hit submit, and it finishes from there.
`start` = beginning the form. `peek` = opening a new tab later and seeing
where it's parked. `resume` = typing the answer in and submitting.

**Done:**
- Installed `langgraph-checkpoint-sqlite` (added to `requirements.txt`),
  deliberately instead of the simpler in-memory `MemorySaver` — proving
  "survives a process restart" honestly needs a checkpointer backed by an
  actual file, not RAM. Added `*.db` to `.gitignore` for the resulting
  runtime checkpoint file, same treatment as `.env`.
- Built `scratch/scratch_interrupt.py`: a two-node graph (`ask`, which
  calls `interrupt()` to pause and surface a question; `finalize`, which
  runs after) compiled with a `SqliteSaver` checkpointer keyed by a fixed
  `thread_id`. Three CLI modes: `start` (kick off a run), `peek` (read
  back current state with no run), `resume` (continue with
  `Command(resume=answer)`).
- Ran all three modes as three genuinely separate `python` process
  invocations, not simulated inside one script — the point was to prove
  persistence, not just narrate it:
  - `start`: `ask` ran, hit `interrupt()`, and `.invoke()` returned
    immediately (no crash, no exception) with an `__interrupt__` key
    containing the question payload.
  - `peek`, from a fresh process: `get_state()` returned the exact same
    `topic`, `next=('ask',)`, and the same pending `Interrupt` — read
    entirely from disk, with nothing carried over from the first
    process's memory.
  - `resume`, from a third fresh process: `Command(resume="apologetic")`
    completed `ask`, ran `finalize`, and returned the correct final state
    (`note: "A apologetic note about the Q3 release delay."`).
- Went one level deeper than the roadmap's own SESSION 4 prompt asked for
  and actually inspected the SQLite file's raw contents rather than
  trusting the mechanism as a black box: opened `interrupt_demo.db`
  directly, found two tables (`checkpoints`, `writes`), and decoded a raw
  checkpoint blob with LangGraph's own `JsonPlusSerializer` back into a
  Python dict to confirm what's actually on disk — a chain of full-state
  snapshots (each row's `parent_checkpoint_id` pointing at the previous
  one), with the pending interrupt stored as a separate row under a
  `__interrupt__` channel rather than inside the snapshot itself.

**Found:** on resume, LangGraph re-runs the interrupted node **from its
start**, not from the `interrupt()` call itself — confirmed by the `[ask]
node running, about to interrupt` print firing a second time on the
`resume` invocation, before the resume value was returned. `interrupt()`
only changes behavior the second time through: instead of pausing again,
it returns the human's answer and lets the function continue. Real design
constraint for the actual `ask_clarifying_questions` node once this is
wired in for real: any code placed *before* the `interrupt()` call inside
a node will execute again on every resume, so it needs to be safe to
repeat (or split into an earlier node that isn't itself interrupted).

**Why this matters going forward:** `ask_clarifying_questions` in the real
`graph.py` currently generates questions and the graph just ends — there's
no way to actually hand it a human's answer and have it continue; it's a
dead end, not a pause. Week 9's real task is adding `interrupt()` inside
(or right after) that node, compiling with a checkpointer, and giving each
requirement a `thread_id` (likely the requirement's own id) so "score ->
ask -> *(human answers, possibly hours later)* -> resume -> generate real
spec" becomes one continuous graph run instead of two disconnected halves.
The re-run-from-the-top behavior found today needs to be designed around
before that node calls the LLM for anything ahead of its `interrupt()`
call.

**Checkpoint met:** today's scoped goal (hands-on interrupt/persist/resume
prep, not the full Week 9 ROADMAP task) — pause, cross-process persistence,
and resume-with-answer all proven with three genuinely separate process
invocations against a real SQLite-backed checkpointer.

**Raw files:** `scratch/scratch_interrupt.py` (new); `requirements.txt`
(added `langgraph-checkpoint-sqlite`); `.gitignore` (added `*.db`) — none
committed yet.

**Aside — Jev (TypeSafe AI's System One model), flagged for a future
experiment, not today's work:** came up in conversation, unrelated to the
interrupt/resume task above. Jev returns typed decisions with calibrated
probabilities in a single pass (no autoregression) instead of generating
text — pitched as a fast/cheap complement to an LLM for structured-decision
steps, not open-ended generation. Architecturally a plausible fit for this
project's `score_testability` step specifically (a calibrated classification
decision), not for the generation nodes, which still need a real LLM. Not
adopting now: cloud-only, closed-weight, ~1 week old early access (released
15 Sep 2026) with no self-host option and no track record yet — too risky a
dependency to wire into a public, reproducible repo at this stage. Worth a
standalone side-experiment sometime (compare it against the current
DeepSeek-based scorer on the same testability cases), not a replacement
decision.

**Correction, same day — pricing checked against TypeSafe's own site, not
a third party:** first pass at this research landed on `jevtypesafeai.com`
(its own footer: "Independent developer platform. Not affiliated with or
endorsed by TypeSafe AI") and its playground/pricing pages, which quote
$0.25-$0.42/M input tokens. Went back and confirmed against `typesafe.ai`
and `docs.typesafe.ai` directly — the real price is **$42 per billion
input tokens ($0.042/M)**, output tokens free; the third-party site's
number is a 6-10x markup, not TypeSafe's actual rate. No dedicated pricing
page exists in TypeSafe's own docs — the $42/B figure is only on their
homepage. Also confirmed first-hand: no self-hosting/on-prem docs anywhere
in TypeSafe's own doc index, so the cloud-only conclusion above holds.
Lesson for later: check a vendor's own domain before trusting a
third-party wrapper's numbers, even when that wrapper is the one offering
the free interactive demo.

**Also found — TypeSafe's own published limitations doc
(`docs.typesafe.ai/model-jaggedness/jev-1.13.md`), directly relevant to
whether Jev would actually help here:** nine documented failure modes,
two matter for this project specifically:
- **No structural-invariant guarantee** — TypeSafe's own words: logically
  equivalent questions aren't guaranteed to produce consistent outputs.
  This is the same non-determinism Week 8 already found in the DeepSeek-
  based scorer (3/4 scored 100, 1/4 scored 85 on identical input) — so
  swapping in Jev would make the routing decision faster and cheaper, not
  more reliable. Changes the framing of the "future experiment" above:
  it's a speed/cost comparison against the current scorer, not a fix for
  the reliability gap.
- **"Jev is not a calculator"** — unreliable at counting/numeric
  comparison, TypeSafe's own recommendation is to keep arithmetic in code
  and reserve Jev for genuine judgment calls. Matches this project's
  existing `compute_testability_score` discipline (model reports boolean
  facts, code does the scoring arithmetic) — if this experiment ever
  happens, keep that split rather than asking Jev to return a number
  directly.

---

## Aside — Instructor vs. baseline scoring experiment, same day (23 Sep 2026)

**Goal:** decided not to chase Jev after all (no vendor lock-in for a
1-week-old product). Instead, tested whether a structured-decoding
library fixes the schema-conformance failure class found in Week 7/8
(`invalid_json` from truncation, a missing required field) — a narrower,
more answerable question than "is there a better judge model." Built on
a separate branch, `experiment/instructor-scoring`, off `main`.

**Done:**
- Compared Instructor (Outlines was ruled out first: its constrained
  decoding needs logit access — a locally-loaded model or a server
  exposing a grammar param like vLLM's `guided_json` — which DeepSeek's
  hosted OpenAI-compatible endpoint doesn't expose; it would degrade to
  the same prompt-and-parse approach already in use, no real improvement).
- Added `instructor` to `requirements.txt`, built
  `scratch/scratch_structured_scoring.py`: runs the same Week 8 three
  requirements (clear/vague/middle) x 5 repeats through two arms —
  unmodified `call_deepseek_json` + `validate_response` (baseline) vs.
  `instructor.from_openai(..., mode=instructor.Mode.JSON)` with
  `response_model=TestabilityScore`, `max_retries=0` (`instructor_strict`,
  a fair single-shot comparison, not conflated with Instructor's separate
  auto-reask feature). Both arms reuse `TestabilityScore`,
  `compute_testability_score`, and the exact same prompt file — nothing
  about the scoring logic is forked or duplicated.

**Found:**
- **Real result, no `--stress` flag needed:** baseline hit a genuine
  `invalid_json` on the `clear` requirement (4/5 valid) — even at
  `MAX_TOKENS=2048`, the Week 7 fix didn't fully close this failure mode.
  `instructor_strict` had zero conformance failures across all 15 calls
  (5 per requirement x 3 requirements). First real evidence that
  schema-in-request measurably reduces this specific failure class.
- **Judgment non-determinism persists identically under both arms** — the
  `middle` requirement ("under 2 seconds in most cases") scored
  inconsistently (55 or 70) whether or not Instructor was used. Confirms
  the prediction going in: structured decoding is a conformance fix, not
  a fix for the model's own judgment varying run to run. Doesn't touch
  the Week 8 finding; both remain true at the same time.
- **Unrelated but worth flagging: installing `instructor` silently
  downgraded `openai` from `3.14.0` to `1.109.1`** in the shared `.venv`
  — pip backtracked all the way to `instructor==1.3.2` to resolve a
  transitive conflict. `.venv` isn't branch-scoped, so this downgrade is
  live even after switching back to `main` until reinstalled. Confirmed
  `llm_client.py` still imports and makes real calls correctly despite
  it (this write-up's own test run proves that), but the downgrade itself
  is exactly the kind of silent, un-pinned dependency drift CLAUDE.md
  already warns about for config — not yet resolved with a proper pin,
  just confirmed harmless for the current call path.

**Why this matters going forward:** Instructor's measured result (zero
conformance failures across 15 calls, vs. one real `invalid_json` on
baseline) is real evidence the approach works — but see the R&D follow-up
below for why it wasn't adopted as-is.

---

### R&D follow-up, same day — root cause of the downgrade, and the decision not to adopt Instructor

**Goal:** the `openai` downgrade above was flagged but not explained.
Dug in rather than accepting or dismissing it on a hunch, since "we don't
feel comfortable using such an old version" is a legitimate reason to
stop and actually verify, not just proceed.

**Found — this is a real, currently unresolvable package-ecosystem
conflict, not a bad pin on our side:**
- Root cause, confirmed by forcing `pip install --dry-run instructor==1.17.0
  openai==3.14.0` (the newest release of each) and reading pip's own
  conflict report: `instructor` depends on `jiter<0.15`, `openai` 3.14.0
  depends on `jiter>=0.16.0` — non-overlapping ranges.
- Checked every instructor release from 1.7.0 through 1.17.0 (its
  latest) against PyPI's own metadata directly: **every single one caps
  `jiter<0.15`.** Instructor has never published a version compatible
  with the `openai` line that requires `jiter>=0.16.0`. `instructor==1.3.2`
  wasn't pip making a poor choice — it's the newest release pip's
  backtracking resolver happened to find that still declares support for
  the older `openai<2.0.0` API, which needs a correspondingly older
  `jiter`. No available pin fixes this; it's upstream.
- Checked whether Outlines (the other candidate, already ruled out
  architecturally — see the original aside above) is at least a cleaner
  dependency: yes. Outlines lists `openai` as an optional, **unpinned**
  extra and has no `jiter` dependency at all, so no version conflict.
  But confirmed (web search, not assumed) that no external hosted API
  currently supports Outlines' actual constrained decoding — its OpenAI
  backend degrades to the same prompt-and-parse approach already in
  `llm_client.py`. Cleaner install, but running our comparison against it
  would just re-test the baseline under a different library name, not
  answer anything new.

**Decision: do not adopt Instructor into `graph.py`, or keep it pinned in
`requirements.txt`.** Neither trade — an old `instructor` (1.3.2) nor a
downgraded `openai` (1.109.1) — is worth taking for a result that a
zero-dependency alternative could plausibly match. Two candidates
identified for next time, neither built yet:
1. `openai` 3.14.0's own native structured-output/`.parse()` method —
   zero new dependencies, but unconfirmed whether DeepSeek's
   OpenAI-compatible endpoint actually honors server-side schema
   constraint vs. just its already-confirmed looser `json_object` mode.
   Needs a real test against DeepSeek to know.
2. A minimal hand-rolled reask-on-validation-error wrapper around the
   existing `call_deepseek_json` + `validate_response`, reusing both
   unmodified — replicates Instructor's retry behavior in a handful of
   lines, no external dependency, no version risk.

**Checkpoint met:** comparison ran end-to-end and produced a real
(not theoretical) result distinguishing conformance failures from
judgment non-determinism; root cause of the dependency conflict
confirmed directly rather than guessed; decision made not to adopt,
with two concrete next candidates identified for a future session.

**Branch disposition:** `experiment/instructor-scoring` stays as the
historical record of this result (script + this write-up) — not merged
into `main`, not deleted. `.venv` should be reverted (`instructor`
uninstalled, `openai` reinstalled to `3.14.0`) since the environment
currently has the downgrade live and isn't branch-scoped. Candidate 1 or
2 above would be the natural next step on this same branch, rather than
opening a new one, since it's the same underlying question
("can decode-time schema enforcement reduce conformance failures against
DeepSeek").

**Raw files:** `requirements.txt` (`instructor` line to be removed on
revert); `scratch/scratch_structured_scoring.py` (kept, not runnable
until `instructor` is reinstalled — intentional, it's a record of a
result, not a maintained tool) — branch `experiment/instructor-scoring`,
not on `main`.

---

## SESSION 4 — Human-in-the-loop interrupts and state persistence (24 Sep 2026)

**Goal:** run the actual `/advanced-learn` SESSION 4 today rather than
waiting for Saturday, building on yesterday's hands-on prep
(`scratch/scratch_interrupt.py`). Scoped goal: fix the specific design
constraint yesterday's session surfaced — LangGraph re-runs an
interrupted node from its start on resume, so any work placed before
`interrupt()` inside a node repeats every time — before touching the real
`ask_clarifying_questions` node.

**Teaching-method finding, worth recording for future sessions in this
project:** household analogies (closet, spice container, waiter/dress)
did not land for this concept, tried five different ones across several
exchanges with no traction. What worked immediately was dropping analogy
entirely and reading a literal table of real checkpoint values (state
dict, `next` tuple) next to the exact code producing them, then actually
running the code and reading real terminal output line by line. For
mechanism-heavy topics (state machines, persistence, anything with a
"what's actually on disk" answer), ground the explanation in real
executed output from the start rather than reaching for a relatable
metaphor first.

**Done:**
- Split the single `ask` node into two: `prepare_question` (does the
  "expensive" work — stands in for the real node's future LLM call —
  and writes a line to `scratch/counter.txt` so its execution count is
  directly observable) and `ask_human` (contains nothing but
  `interrupt(state.question)`). Wired `START -> prepare_question ->
  ask_human -> finalize`.
- Ran `start` -> `peek` -> `resume "curious"` as three genuinely separate
  process invocations against the split graph and confirmed by direct
  inspection, not narration:
  - `counter.txt` had exactly **one** line after the full `start` +
    `resume` cycle — `prepare_question` executed once, never repeated.
  - `"[ask_human] node running, about to interrupt"` printed **twice**
    across the same cycle (once on `start`, once on `resume`) — the
    re-run-from-top rule from yesterday still holds, it's just now
    isolated to a node with nothing costly in it.
- Found and fixed a real bug along the way, not a staged one: the
  original script's hardcoded `THREAD_ID = "demo-thread-1"` combined
  with a never-deleted `interrupt_demo.db` meant a `start` run today
  picked up a **stale, already-completed thread from a previous
  session** — `answer`/`note` showed up already resolved in the very
  first `start` result, before any resume happened. Confirmed via direct
  sqlite inspection (`checkpoints` table had 8 rows already chained for
  `demo-thread-1` before today's run). Same failure class as a Selenium
  test reusing a browser session across test cases without teardown —
  directly relevant to the real graph, since each requirement run needs
  its own `thread_id` or clarifying-question state will bleed across
  requirements.
- Also found the opposite failure mode while fixing the above: switching
  `THREAD_ID` to `f"demo-{uuid.uuid4().hex[:8]}"` (generated fresh per
  process) broke the `start`/`peek`/`resume` CLI pattern entirely — each
  separate `python` invocation got its own random id, so `peek` and
  `resume` opened brand-new empty threads instead of the paused one,
  and `resume` crashed with a Pydantic `topic: Field required` error
  trying to resume a thread that never ran `prepare_question`. Settled
  on a fixed `THREAD_ID = "week9-test-1"` for this repeatable scratch
  test; the `uuid` import is left in, unused, for whenever this file
  is adapted to generate one id per run and pass it through explicitly
  instead of regenerating it per process.

**Why this matters going forward:** confirms the exact fix needed for
the real `ask_clarifying_questions` node in `graph.py` — its LLM call
(question generation) must live in a node that completes *before* any
`interrupt()` call, not inside the same node as the interrupt. Also
confirms the real graph will need a `thread_id` derived from something
stable per requirement (e.g. the requirement's own id), generated once
and passed through explicitly — not regenerated per process, and not a
shared constant either.

**Checkpoint met:** SESSION 4's scoped goal — proved with real, directly
observed evidence (a counter file, not an assertion) that splitting
expensive work out of an interrupting node avoids repeating it on resume,
and hit two real, previously-undiscovered bugs (stale shared thread,
broken per-process random thread) in the process of proving it.

**Raw files:** `scratch/scratch_interrupt.py` (modified — two-node
split, fixed `THREAD_ID`) — not yet committed. `scratch/counter.txt` and
`scratch/interrupt_demo.db` were test artifacts, deleted, not committed
(the `.db` is gitignored anyway).

**Not done today, deliberately:** the real Week 9 task — wiring this
same split into `ask_clarifying_questions` in `graph.py`, plus giving
the compiled graph a real checkpointer and a per-requirement
`thread_id`. That's a design call (how the node splits, what state
fields change), Pratham's first draft per the usual split, picked up
fresh next session.

---

## Aside — Laya vs. baseline scoring experiment (25 Sep 2026)

**Goal:** same shape of question as the Jev and Instructor asides above —
whether Laya (`convaiinnovations/laya`, Apache 2.0, self-hosted,
open-weight) can replace or complement the DeepSeek-based
`score_testability` node. Raised because it's pitched as an open,
self-hostable equivalent of Jev's typed-decision architecture, which would
remove the exact objection (cloud-only, closed-weight) that parked Jev.
Built on a separate branch, `experiment/laya-scoring`, off `main` at
`27b9e45`, in its own git worktree with a fully isolated `.venv` (not the
shared one — deliberately, after the Instructor experiment's shared-venv
`openai` downgrade).

**Done:**
- Hand-labeled 8 requirements (the original 3 clear/vague/middle canonical
  texts plus 5 new ones, added so all 4 `score_testability` criteria —
  not just `has_measurable_condition` — had clean examples) against the
  same 4 booleans the production scorer computes.
- Wired Laya's `noul` (boolean) question primitive to the *same, unreworded*
  criterion wording from `prompts/testability_score_v1.txt`, so any
  accuracy gap reflects the model, not different question phrasing.
- Ran both arms — Laya (`router.predict`) and the real, unmodified
  `call_deepseek_json` + `validate_response` baseline — on the same 8
  texts, through the same unmodified `compute_testability_score()`, so
  nothing about the scoring arithmetic is forked per arm.
- Each Laya call repeated 3x per requirement to check determinism; the
  `middle` case ("under 2 seconds in most cases") deliberately left
  unlabeled and excluded from the accuracy tally, since Week 8 already
  found the baseline itself disagrees with itself on that exact text.

**Found — real numbers, `scratch/scratch_laya_scoring.py` SUMMARY output:**
- **Accuracy, Laya vs. hand-labels (excl. contested `middle`), 28 checks:**
  `has_measurable_condition` 5/7 (71%), `has_vague_qualitative_language`
  6/7 (86%), `has_ambiguous_scope` 4/7 (57%), `missing_precondition` 2/7
  (**29%**) — overall **17/28 (61%)**.
- **Same 28 checks, baseline (DeepSeek, current production scorer):**
  100%, 100%, 100%, 86% — overall **27/28 (96%)**, 0/24 invalid-JSON
  responses.
- **Calibration — confidence ≥0.8 but wrong:** all 4 occurrences are on
  the *same* criterion, `missing_precondition` (confidences 0.82, 0.90,
  0.81, 0.83 on `clear_login`, `vague_fast`, `vague_checkout_ux`,
  `vague_error_handling` respectively). Not scattered noise — Laya is
  both the least accurate and the most overconfident specifically on
  that one criterion.
- **Determinism:** all 32 (requirement, criterion) pairs exactly
  repeatable across 3 runs each — confirms the expected non-autoregressive,
  no-sampling behavior; a genuine point in Laya's favor.
- **Latency:** Laya warm mean 1.44s per call answering all 4 criteria at
  once (~0.36s/criterion) vs. baseline's 3.01s per single-criterion call
  — Laya is meaningfully cheaper/faster per criterion, consistent with
  the original pitch.
- **The earlier single-criterion spot check generalized, not a fluke:**
  on the contested `middle` text, Laya again read the numeric "under 2
  seconds" threshold as *not* measurable, confidently (`has_measurable_
  condition` p=0.08, confidence=0.92) — same direction and same
  confident-wrongness as the original 3-point probe that motivated
  building this full script in the first place.

**Addendum, same day — checked whether we ran Laya wrong before trusting
the accuracy numbers above, not just assumed the setup was fine:**
prompted by "are we using Laya wrong, full fp16 or quantized?" Read the
actual installed source (`laya/agent.py`, `laya/common.py`), not the
package's marketing copy or docstrings alone.
- **No quantization path exists anywhere in this library.** Searched the
  whole `laya` source for int8/bitsandbytes/quantization handling —
  there is none. Not a lever we failed to pull; it isn't offered.
- **We ran full fp32 compute, not fp16.** The checkpoint's weights are
  stored on disk as fp16 (`model.safetensors`, confirmed earlier), but
  `common.py:build_model` never passes a `torch_dtype` when constructing
  the encoder, so the model's parameters are built in PyTorch's default
  fp32. `agent.py:335`'s `load_state_dict(weights, strict=True)` then
  copies the fp16-stored values into those fp32 tensors — an upcast, not
  a downcast. `agent.py:392-407`'s device/dtype policy only enables
  fp16/bf16 autocast on CUDA or MPS; on our CPU-only machine `self.dtype`
  stays `torch.float32` and `amp_enabled=False` unless `LAYA_CPU_AMP=bf16`
  is set explicitly, which our script didn't set. So this run used *more*
  numerical precision than the checkpoint's native fp16 format, not less
  — precision loss does not explain the 61% vs. 96% accuracy gap.
- **Other usage checked and found correct, not a fallback/degraded path:**
  `Router.predict`'s signature explicitly types `state` as `str | dict |
  list` — passing the raw requirement string directly (what the script
  does) is a first-class documented input, not a workaround. Question
  primitive (`noul`) and checkpoint (`english`, auto-routed) both match
  the reasoning already recorded above. The one thing genuinely not
  exercised is batched inference (`predict_batch`/`route_batch`) instead
  of looping single `predict()` calls — a throughput question, not an
  accuracy one; it doesn't change what the model computes per item.
- **Working hypothesis for the gap, architectural rather than a setup
  bug:** `missing_precondition`'s phrasing ("fail to state an explicit
  trigger...") is a double-negative-style judgment a small classifier
  head may just handle worse than an LLM does, independent of precision.
  Untested — would need the reworded-question experiment noted below to
  confirm.

**Decision (draft — for your review, not yet final):** the accuracy gap
(61% vs. 96%) plus a concentrated, overconfident failure mode on
`missing_precondition` reads as a real result against adopting Laya as a
replacement or complement for `score_testability` right now — same bar
the Instructor experiment used ("a measured result decides, not 'should
work'"). Determinism and per-call latency are real, measured points in
Laya's favor if this is ever revisited, e.g. narrowed to the 3 criteria
it scored better on, or with `missing_precondition`'s question reworded
(which would reopen the fairness-constraint tradeoff this run
deliberately avoided).

**Branch disposition (draft, pending your call):** by the same pattern as
`experiment/instructor-scoring` — likely keep `experiment/laya-scoring`
as the historical record (script + this write-up), not merged into
`main`, not deleted. No shared-venv cleanup needed this time, since this
worktree's `.venv` was isolated from the start.

**Raw files:** `scratch/scratch_laya_scoring.py` (new, untracked),
`scratch/laya_run_output.log` (new, untracked — full run output behind
the SUMMARY above), `requirements.txt` (modified — `laya` appended,
last line). None committed; per CLAUDE.md, Claude does not run
`git add`/`commit`/`push` here.
