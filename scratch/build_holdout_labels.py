"""
Builds the held-out validation slice for the Laya fine-tuning dataset.

Unlike scratch/finetune_dataset_claude_v1.jsonl (Claude-authored text AND
labels), the texts here are Claude-authored but the LABELS come from the
real, unmodified production scorer (call_deepseek_json + validate_response
against testability_score_v1.txt) -- so this file measures "does the
fine-tuned model agree with the actual production judge," independent of
Claude's own labeling judgment. Kept separate from the training set on
purpose; never merge the two files.
"""

import json

from llm_client import call_deepseek_json
from schemas import TestabilityScore, validate_response

with open("prompts/testability_score_v1.txt", encoding="utf-8") as f:
    SCORE_PROMPT = f.read()

with open("scratch/finetune_holdout_texts.txt", encoding="utf-8") as f:
    texts = [line.strip() for line in f if line.strip()]

print(f"Labeling {len(texts)} held-out texts via the real DeepSeek scorer...")

results = []
invalid = []
for i, text in enumerate(texts):
    prompt = SCORE_PROMPT.format(requirement=text)
    result = call_deepseek_json(prompt)
    status, detail = validate_response(result.text, TestabilityScore)
    if status != "valid":
        invalid.append((text, status))
        print(f"  [{i+1}/{len(texts)}] INVALID ({status}): {text[:60]}")
        continue
    row = {
        "text": text,
        "has_measurable_condition": detail.has_measurable_condition,
        "has_vague_qualitative_language": detail.has_vague_qualitative_language,
        "has_ambiguous_scope": detail.has_ambiguous_scope,
        "missing_precondition": detail.missing_precondition,
        "reasoning": detail.reasoning,
    }
    results.append(row)
    print(f"  [{i+1}/{len(texts)}] ok: {text[:60]}")

with open("scratch/finetune_holdout_deepseek_labels.jsonl", "w", encoding="utf-8") as f:
    for row in results:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

print(f"\nWrote {len(results)} labeled rows to scratch/finetune_holdout_deepseek_labels.jsonl")
if invalid:
    print(f"{len(invalid)} invalid/skipped (see above)")
