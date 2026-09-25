"""
Follow-up to scratch_laya_scoring.py, NOT a replacement for it.

Tests one specific hypothesis raised after reading Laya's own model card
(convaiinnovations/laya README, "Honest Limits"): `noul` questions can anchor
on their own false:/true: option labels instead of reading the state,
"most strongly on this English checkpoint" (GH issue #156). The README's own
suggested workaround is to ask the same question as a two-option `choice`
with neutral keys instead.

`missing_precondition` was the worst-performing criterion in the main script
(29% accuracy, and the *only* criterion with any confidently-wrong answers)
and it happens to be phrased as a negation ("does the requirement FAIL to
state...") -- exactly the shape where label-anchoring would bite hardest.

Design: change ONLY missing_precondition from noul to choice. Leave the other
3 criteria as noul, unchanged, so this is a single-variable comparison against
the main script's run, not a wholesale methodology change. This deliberately
does NOT touch the main script's fairness constraint (verbatim noul wording)
for the other 3 criteria.
"""

import time

from laya import Router

N_REPEATS = 3

CRITERIA = [
    "has_measurable_condition",
    "has_vague_qualitative_language",
    "has_ambiguous_scope",
    "missing_precondition",
]

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
    # Changed from noul -> choice. Same underlying question, neutral A/B keys,
    # per the README's own suggested workaround for noul's label-anchoring bug.
    "missing_precondition": {
        "type": "choice",
        "instructions": "Does the requirement fail to state an explicit trigger or precondition for when it applies?",
        "criteria": {
            "A": "yes, the requirement fails to state an explicit trigger or precondition",
            "B": "no, the requirement does state an explicit trigger or precondition",
        },
    },
}

REQUIREMENTS = [
    ("clear_login", "The system must lock a user account after 5 failed login attempts.", False),
    ("vague_fast", "The system should be fast.", True),
    ("middle_2s", "The system must respond in under 2 seconds in most cases.", None),
    ("vague_login_support", "The application shall support user login.", True),
    (
        "clear_payment_approval",
        "When a user submits a payment of more than $10,000, the system must "
        "require secondary approval before processing.",
        False,
    ),
    ("vague_checkout_ux", "The system should provide a good user experience during checkout.", True),
    (
        "clear_reengagement_email",
        "If the user's account has been inactive for 90 days, the system must "
        "send a re-engagement email.",
        False,
    ),
    ("vague_error_handling", "The system must handle errors gracefully.", True),
]


def run_laya(router: Router, text: str) -> dict:
    result = router.predict(text, LAYA_QUESTIONS)
    ans = result["answers"]["missing_precondition"]
    bool_val = ans["choice"] == "A"
    # answer_confidence, NOT confidence: common.py's own docstring says
    # answer_confidence (= max(p)) is the calibrated, ECE-measured quantity;
    # confidence for `choice` answers is an uncalibrated entropy measure
    # instead (they only coincide for `noul`, which is why the original
    # script's use of `confidence` there was fine but this would not be).
    conf = float(ans["answer_confidence"])
    return {"bool": bool_val, "confidence": conf, "raw": ans}


def main():
    print("=== Loading Laya (english checkpoint), missing_precondition as choice ===")
    t0 = time.time()
    router = Router(device="cuda")
    router.predict("warmup", LAYA_QUESTIONS)
    print(f"Warm-up (incl. first load) took {time.time()-t0:.2f}s\n")

    correct = 0
    total = 0
    wrong_confident = []
    determinism_breaks = []
    latencies = []

    for key, text, expected in REQUIREMENTS:
        runs = []
        for _ in range(N_REPEATS):
            t0 = time.time()
            r = run_laya(router, text)
            latencies.append(time.time() - t0)
            runs.append(r)

        choices = [r["bool"] for r in runs]
        if len(set(choices)) > 1:
            determinism_breaks.append((key, choices))

        first = runs[0]
        tag = ""
        if expected is None:
            tag = "(contested, not scored)"
        else:
            total += 1
            if first["bool"] == expected:
                correct += 1
            else:
                tag = "<- WRONG"
                if first["confidence"] >= 0.8:
                    wrong_confident.append((key, first["confidence"]))
                    tag = "<- WRONG, confidently (%.2f)" % first["confidence"]
        print(f"--- {key} --- bool={first['bool']!s:5s} conf={first['confidence']:.3f} expected={expected!s:5s} {tag}")

    print("\n=== SUMMARY (missing_precondition, choice-format variant) ===")
    print(f"  accuracy: {correct}/{total} ({100*correct/total:.0f}%)")
    print(f"  (main script's noul-format result for this criterion: 2/7, 29%)")
    print(f"  confidently wrong (conf >= 0.8): {wrong_confident if wrong_confident else 'none'}")
    if determinism_breaks:
        for key, values in determinism_breaks:
            print(f"  NON-DETERMINISTIC: {key}: {values}")
    else:
        print(f"  determinism: all {len(REQUIREMENTS)} repeats (x{N_REPEATS}) exactly repeatable")
    print(f"  latency: mean={sum(latencies)/len(latencies):.3f}s min={min(latencies):.3f}s max={max(latencies):.3f}s n={len(latencies)}")


if __name__ == "__main__":
    main()
