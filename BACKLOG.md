# Backlog — Deferred Ideas

Ideas raised during the build that were deliberately deferred, with the
reasoning and the condition under which to revisit them.

---

## Number-grounding check for generated specs (parked 6 Oct 2026)

**What:** flag a spec that contains a value (number, duration, limit) not
supported by the requirement it was generated from.

**Why parked:** a literal "number not in the requirement" check flagged 7/18
specs (10/18 on the v2 prompt) and every flag was benign (derived values,
unit conversions, labels like T0/T1). A hard gate would block good specs; a
warning on every flagged spec would be ignored.

**Plan (agreed direction, not started):**
1. Hand-label about 20 specs: grounded vs has an invented value (Pratham).
2. Build an LLM judge and measure it against those labels (the P1 harness
   fits here).
3. Feed the judge's verdict into `spec_warnings`, warning-only, never
   blocking.

**Revisit:** when Pratham starts writing requirements and the labeled set.

## Consistency check on a labelled benchmark set (parked 6 Oct 2026)

**What it is:** the set-level consistency check (`consistency.py`) passes its
invented eval set (50/50 planted conflicts caught, 0 false alarms in 45
near-miss/clean runs) but did not catch a known contradiction in a larger,
independently labelled requirement set. Invented cases were written alongside
the prompt, so they overstate how well it works on other input.

**Findings so far:**
- One call over an 8-requirement set exhausted even a 16,384-token reasoning
  budget and returned nothing (reported honestly as `not_checked`).
- Comparing all 28 pairs completed, but found 0 conflicts, missing a
  contradiction that takes one inference step (an example's outcome only
  contradicts a rule once a precedence rule is applied).
- Testability scores are not stable across runs: the same requirement scored
  100 once and 85 on the next run.

**Plan (agreed direction):**
1. Keep a small labelled benchmark outside the repo: requirement text plus
   hand-labelled true issues. Only aggregate numbers go in NOTES.md.
   (Done 7 Oct; scorer is `evals/labelled_benchmark.py`.)
2. Try fixes against that ground truth, cheapest first, keep what finds the
   known issues: (a) one example-versus-rules call per requirement that has an
   example (built, see NOTES.md); (b) extract trigger/condition/outcome per
   requirement, then compare the structured rules; (c) a different model for
   this step.
3. Report issues caught, missed and falsely raised on the labelled benchmark,
   not only the invented set. An invented case mirroring the two-step
   inference is added (`P_two_step_example_vs_rule`).
4. Make splitting a document into requirements automatic and visible.

**Needs from Pratham (judgment):** more labelled sets, ideally with a known
issue each; whether option (c) is worth trying.
