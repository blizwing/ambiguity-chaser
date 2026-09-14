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
