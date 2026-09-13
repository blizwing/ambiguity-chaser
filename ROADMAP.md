# Roadmap — Phase 2: Ambiguity Chaser

Copied from the master six-month roadmap in `eval-harness/ROADMAP.md`, which
still holds the full three-phase plan, the red flags, and the closing
narrative. This file carries only what's needed to work day to day in this
repo.

**Phase 2 dates:** September – November 2026.
**Proves:** agentic dev + GenAI.

Week-level only, on purpose. Daily detail comes when you get there — writing
November's steps in September would be fiction.

---

## How to read a week

- **LEARN** — `/advanced-learn` sessions land on Saturdays, one per listed
  week. Everything else is doc-reading or build, same rhythm as Phase 1.
- **BUILD** — what gets written that week, broken into days once you arrive.
- **DONE WHEN** — the week's checkpoint, same discipline as Phase 1: can't
  tick it, the week isn't finished.

---

## Week-by-week

**Week 6** — LangGraph fundamentals → **SESSION 3**
**Week 7** — Port Phase 1 prompt into a single-node graph
**Week 8** — Conditional edges: score → "emit spec" or "ask questions"
**Week 9** — Human-in-the-loop interrupt → **SESSION 4**
**Week 10** — Re-ask loop + max-iteration guard
**Week 11** — Tool calling: coverage check
**Week 12** — Embeddings + retrieval → **SESSION 5**
**Week 13** — Schema-validated spec emission
**Week 14** — Point the Phase 1 harness at the agent
**Week 15** — Polish, ship, second message to seniors

---

### SESSION 3 prompt — Week 6, Saturday

```
/advanced-learn LangGraph for building stateful agents

Context: QA automation engineer, Java/Selenium background, just shipped an LLM eval
harness in Python so I'm comfortable with API calls, Pydantic and structured output.
I've never built an agent. I'm building a system where an agent reads a vague
software requirement, scores how testable it is, and either emits a structured test
spec or generates clarifying questions and waits for a human answer before
continuing. I need to understand nodes, edges, and state properly — not a toy
chatbot demo. Tell me what to ignore in the LangGraph docs, because I know there's a
lot there I don't need yet.
```

### SESSION 4 prompt — Week 9, Saturday

```
/advanced-learn human-in-the-loop interrupts and state persistence in LangGraph

Context: I have a working LangGraph agent with conditional edges that scores
requirement testability. Now the hard part: when the score is low, the graph must
pause, surface clarifying questions to a human, wait — possibly for hours — and then
resume with state intact. I need checkpointing, interrupt patterns, and how state
survives a process restart. I'm a QA engineer so I care a lot about the failure
modes: what happens if the process dies mid-pause, and how do I test a graph that's
designed to stop halfway.
```

### SESSION 5 prompt — Week 12, Saturday

```
/advanced-learn embeddings and retrieval quality measurement

Context: QA engineer building an agent that checks whether a new requirement is
already covered by an existing test case. I need semantic search over a corpus of a
few hundred test cases. I have an MSc in ML so I understand vector spaces and
cosine similarity conceptually — what I don't have is practical judgment: which
embedding model, chunking strategy for short structured text, and above all how to
*measure* whether retrieval is actually good rather than assuming it is. Treat
retrieval precision as something to be tested, not trusted.
```

---

## Red flags (same ones that governed Phase 1)

- **Redesigning something that already works** → scope creep.
- **Three buffer days in a row spent catching up** → budget's wrong, cut to
  1 hr/day, don't abandon.
- **Reaching back into eval-harness to rebuild something already decided
  there** (e.g. `LLMClient`) → port and adapt, don't redesign from scratch
  for its own sake.

---

Full three-phase context, the P1 build log, and the closing narrative this
whole plan builds toward live in `eval-harness/ROADMAP.md` and
`eval-harness/NOTES.md`.
