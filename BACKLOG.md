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
