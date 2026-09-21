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
