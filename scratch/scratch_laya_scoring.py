"""
Full evaluation of Laya (convaiinnovations/laya, Apache 2.0, self-hosted) as a
candidate replacement/complement for the DeepSeek-based score_testability
scorer, following the same aside pattern as the Jev research note and the
Instructor experiment (see NOTES.md).

Method:
- 8 requirements, hand-labeled by us against the same 4 criteria the real
  prompt (prompts/testability_score_v1.txt) already asks DeepSeek to judge.
  Labels are "expected ground truth" except where noted `None` (contested/
  boundary case) -- 'middle' is deliberately left contested, since Week 8
  already found the DeepSeek baseline itself disagrees with itself run to
  run on that exact case (55 vs 70).
- Laya's 4 noul questions are worded directly from the same criterion
  definitions in testability_score_v1.txt, not reworded independently, so
  this is a fair zero-shot comparison, not a strawman.
- Each text run N_REPEATS times through both Laya (English checkpoint,
  auto-routed) and the real baseline (call_deepseek_json + validate_response,
  unmodified) to separately check:
    1. accuracy vs. our expected labels
    2. agreement with the current production scorer
    3. determinism (Laya: exact-match repeats expected, no sampling in an
       encoder forward pass; baseline: known non-deterministic per Week 8)
    4. calibration (does confidence track correctness, or is it confidently
       wrong -- directly relevant to this project's core "confident spec
       beats a pause" risk, see CLAUDE.md)
- Laya's noul->bool projection uses the exact same `>= 0.5` threshold
  laya.structured._project uses internally, not a value we chose ourselves.
- The derived score for both arms goes through the same unmodified
  compute_testability_score -- nothing about the scoring arithmetic is
  forked between arms.

This is NOT a fine-tuning experiment. TypeSafe/Convai's own published
numbers (see NOTES.md Laya aside) say zero-shot is expected to be well
below a fine-tuned checkpoint's numbers -- this script measures exactly
how far off zero-shot is on OUR schema, on OUR real examples, not a
generic benchmark.
"""

import time

from laya import Router

from llm_client import call_deepseek_json
from schemas import TestabilityScore, compute_testability_score, validate_response

N_REPEATS = 3

CRITERIA = [
    "has_measurable_condition",
    "has_vague_qualitative_language",
    "has_ambiguous_scope",
    "missing_precondition",
]

# Worded directly from prompts/testability_score_v1.txt's own criterion
# definitions -- not reworded, so Laya is judged on the same rubric DeepSeek is.
LAYA_QUESTIONS = {
    "has_measurable_condition": {
        "type": "noul",
        "instructions": (
            "Does the requirement contain at least one measurable or verifiable "
            "condition -- a number, a named field/value, or a concrete state change?"
        ),
    },
    "has_vague_qualitative_language": {
        "type": "noul",
        "instructions": (
            "Does the requirement rely on a vague qualitative word with no "
            "quantifier (e.g. 'fast', 'appropriate', 'reasonable', 'secure', "
            "'user-friendly')?"
        ),
    },
    "has_ambiguous_scope": {
        "type": "noul",
        "instructions": "Could the requirement's expected outcome reasonably be read more than one way?",
    },
    "missing_precondition": {
        "type": "noul",
        "instructions": (
            "Does the requirement fail to state an explicit trigger or "
            "precondition for when it applies?"
        ),
    },
}

with open("prompts/testability_score_v1.txt", mode="r", encoding="utf-8") as f:
    SCORE_PROMPT = f.read()

# (key, text, expected_labels) -- expected_labels[criterion] is True/False, or
# None where we deliberately leave the ground truth contested.
REQUIREMENTS = [
    (
        "clear_login",
        "The system must lock a user account after 5 failed login attempts.",
        {
            "has_measurable_condition": True,
            "has_vague_qualitative_language": False,
            "has_ambiguous_scope": False,
            "missing_precondition": False,
        },
    ),
    (
        "vague_fast",
        "The system should be fast.",
        {
            "has_measurable_condition": False,
            "has_vague_qualitative_language": True,
            "has_ambiguous_scope": True,
            "missing_precondition": True,
        },
    ),
    (
        "middle_2s",
        "The system must respond in under 2 seconds in most cases.",
        {
            # Contested on purpose -- Week 8 found the current scorer itself
            # disagrees run to run on this one (55 vs 70). Reported separately,
            # not folded into the accuracy rate.
            "has_measurable_condition": None,
            "has_vague_qualitative_language": None,
            "has_ambiguous_scope": None,
            "missing_precondition": None,
        },
    ),
    (
        "vague_login_support",
        "The application shall support user login.",
        {
            "has_measurable_condition": False,
            "has_vague_qualitative_language": False,
            "has_ambiguous_scope": True,
            "missing_precondition": True,
        },
    ),
    (
        "clear_payment_approval",
        "When a user submits a payment of more than $10,000, the system must "
        "require secondary approval before processing.",
        {
            "has_measurable_condition": True,
            "has_vague_qualitative_language": False,
            "has_ambiguous_scope": False,
            "missing_precondition": False,
        },
    ),
    (
        "vague_checkout_ux",
        "The system should provide a good user experience during checkout.",
        {
            "has_measurable_condition": False,
            "has_vague_qualitative_language": True,
            "has_ambiguous_scope": True,
            "missing_precondition": True,
        },
    ),
    (
        "clear_reengagement_email",
        "If the user's account has been inactive for 90 days, the system must "
        "send a re-engagement email.",
        {
            "has_measurable_condition": True,
            "has_vague_qualitative_language": False,
            "has_ambiguous_scope": False,
            "missing_precondition": False,
        },
    ),
    (
        "vague_error_handling",
        "The system must handle errors gracefully.",
        {
            "has_measurable_condition": False,
            "has_vague_qualitative_language": True,
            "has_ambiguous_scope": True,
            "missing_precondition": True,
        },
    ),
]


def run_laya(router: Router, text: str) -> dict:
    result = router.predict(text, LAYA_QUESTIONS)
    out = {}
    for crit in CRITERIA:
        ans = result["answers"][crit]
        p_true = float(ans["noul"])
        out[crit] = {
            "bool": p_true >= 0.5,  # same threshold laya.structured._project uses
            "p_true": p_true,
            "confidence": float(ans["confidence"]),
        }
    return out


def run_baseline(text: str) -> dict:
    prompt = SCORE_PROMPT.format(requirement=text)
    result = call_deepseek_json(prompt)
    status, detail = validate_response(result.text, TestabilityScore)
    if status != "valid":
        return {"status": status}
    return {"status": "valid", "detail": detail}


def laya_score(bools: dict) -> int:
    ts = TestabilityScore(
        has_measurable_condition=bools["has_measurable_condition"]["bool"],
        has_vague_qualitative_language=bools["has_vague_qualitative_language"]["bool"],
        has_ambiguous_scope=bools["has_ambiguous_scope"]["bool"],
        missing_precondition=bools["missing_precondition"]["bool"],
        reasoning="n/a (laya has no free-text generation)",
    )
    return compute_testability_score(ts)


def main():
    print(f"=== Loading Laya (english checkpoint) ===")
    t0 = time.time()
    router = Router(device="cuda")
    # Warm the checkpoint now so per-item timings below reflect steady state,
    # not the one-time lazy-load cost.
    router.predict("warmup", {"has_measurable_condition": LAYA_QUESTIONS["has_measurable_condition"]})
    print(f"Warm-up (incl. first load) took {time.time()-t0:.2f}s\n")

    per_criterion_correct = {c: 0 for c in CRITERIA}
    per_criterion_total = {c: 0 for c in CRITERIA}
    per_criterion_wrong_confident = {c: [] for c in CRITERIA}
    determinism_breaks = []
    laya_latencies = []

    baseline_per_criterion_correct = {c: 0 for c in CRITERIA}
    baseline_per_criterion_total = {c: 0 for c in CRITERIA}
    baseline_invalid = 0
    baseline_latencies = []

    for key, text, expected in REQUIREMENTS:
        print(f"--- {key}: {text!r} ---")
        laya_runs = []
        for i in range(N_REPEATS):
            t0 = time.time()
            r = run_laya(router, text)
            laya_latencies.append(time.time() - t0)
            laya_runs.append(r)

        # Determinism check: do repeats agree exactly on p_true?
        for crit in CRITERIA:
            p_values = [round(r[crit]["p_true"], 6) for r in laya_runs]
            if len(set(p_values)) > 1:
                determinism_breaks.append((key, crit, p_values))

        laya_first = laya_runs[0]
        for crit in CRITERIA:
            exp = expected[crit]
            got = laya_first[crit]["bool"]
            conf = laya_first[crit]["confidence"]
            p_true = laya_first[crit]["p_true"]
            tag = ""
            if exp is None:
                tag = "(contested, not scored)"
            else:
                per_criterion_total[crit] += 1
                if got == exp:
                    per_criterion_correct[crit] += 1
                else:
                    tag = "<- WRONG"
                    if conf >= 0.8:
                        per_criterion_wrong_confident[crit].append((key, conf))
                        tag = "<- WRONG, confidently (%.2f)" % conf
            print(f"  laya  {crit:32s} p_true={p_true:.3f} conf={conf:.3f} bool={got!s:5s} expected={exp!s:5s} {tag}")

        score = laya_score(laya_first)
        print(f"  laya derived score: {score}")

        baseline_runs = []
        for i in range(N_REPEATS):
            t0 = time.time()
            r = run_baseline(text)
            baseline_latencies.append(time.time() - t0)
            baseline_runs.append(r)

        valid_runs = [r for r in baseline_runs if r["status"] == "valid"]
        baseline_invalid += N_REPEATS - len(valid_runs)
        if valid_runs:
            b = valid_runs[0]["detail"]
            for crit in CRITERIA:
                exp = expected[crit]
                got = getattr(b, crit)
                if exp is not None:
                    baseline_per_criterion_total[crit] += 1
                    if got == exp:
                        baseline_per_criterion_correct[crit] += 1
            scores = [compute_testability_score(r["detail"]) for r in valid_runs]
            print(f"  baseline scores across {len(valid_runs)} valid run(s): {scores}")
        else:
            print(f"  baseline: no valid runs ({N_REPEATS - len(valid_runs)} invalid)")
        print()

    print("=== SUMMARY ===\n")
    print("-- Laya zero-shot accuracy vs. our expected labels (excludes contested 'middle' case) --")
    for crit in CRITERIA:
        total = per_criterion_total[crit]
        correct = per_criterion_correct[crit]
        pct = 100 * correct / total if total else float("nan")
        print(f"  {crit:32s} {correct}/{total} ({pct:.0f}%)")
    overall_correct = sum(per_criterion_correct.values())
    overall_total = sum(per_criterion_total.values())
    print(f"  {'OVERALL':32s} {overall_correct}/{overall_total} ({100*overall_correct/overall_total:.0f}%)\n")

    print("-- Baseline (DeepSeek, current production scorer) accuracy vs. the same labels --")
    for crit in CRITERIA:
        total = baseline_per_criterion_total[crit]
        correct = baseline_per_criterion_correct[crit]
        pct = 100 * correct / total if total else float("nan")
        print(f"  {crit:32s} {correct}/{total} ({pct:.0f}%)")
    b_overall_correct = sum(baseline_per_criterion_correct.values())
    b_overall_total = sum(baseline_per_criterion_total.values())
    print(f"  {'OVERALL':32s} {b_overall_correct}/{b_overall_total} ({100*b_overall_correct/b_overall_total:.0f}%)")
    print(f"  baseline invalid_json/invalid responses: {baseline_invalid}/{len(REQUIREMENTS)*N_REPEATS}\n")

    print("-- Determinism (Laya, identical input repeated) --")
    if determinism_breaks:
        for key, crit, values in determinism_breaks:
            print(f"  NON-DETERMINISTIC: {key}/{crit}: {values}")
    else:
        print(f"  All {len(REQUIREMENTS)*len(CRITERIA)} (requirement, criterion) pairs were exactly repeatable across {N_REPEATS} runs.")
    print()

    print("-- Confidently wrong answers (confidence >= 0.8 but bool != expected) --")
    any_confident_wrong = False
    for crit, items in per_criterion_wrong_confident.items():
        for key, conf in items:
            any_confident_wrong = True
            print(f"  {key}/{crit}: confidence={conf:.2f}")
    if not any_confident_wrong:
        print("  none")
    print()

    print("-- Latency --")
    print(f"  laya predict() (warm, 4 questions/call): mean={sum(laya_latencies)/len(laya_latencies):.3f}s  "
          f"min={min(laya_latencies):.3f}s max={max(laya_latencies):.3f}s  n={len(laya_latencies)}")
    print(f"  baseline call_deepseek_json (1 question/call): mean={sum(baseline_latencies)/len(baseline_latencies):.3f}s  "
          f"min={min(baseline_latencies):.3f}s max={max(baseline_latencies):.3f}s  n={len(baseline_latencies)}")


if __name__ == "__main__":
    main()
