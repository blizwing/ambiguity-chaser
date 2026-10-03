"""
Measures retrieval quality instead of trusting it (Week 12). Run from the
repo root:  python -m evals.retrieval_eval

Compares Week 11's keyword search against embedding search on a labeled
query set, and prints the score distributions needed to pick MIN_SCORE.
Retrieval only: whether a retrieved case truly *covers* the requirement is
the LLM verdict's job, so near-misses count as hits here if the right
test case is retrieved.
"""

import json

import retrieval
import tools

with open("evals/retrieval_queries.json", encoding="utf-8") as f:
    QUERIES = json.load(f)


def keyword_ids(query: str) -> list[str]:
    return [tc["id"] for tc in tools.keyword_search(query)]


def semantic_ids(query: str) -> list[str]:
    return [tc["id"] for _, tc in retrieval.score_all(query)[:3]]  # unthresholded


def rank_of(expected: str, ids: list[str]) -> int | None:
    return ids.index(expected) + 1 if expected in ids else None


def main() -> None:
    positives = [q for q in QUERIES if q["expected"]]
    for name, fn in [("keyword", keyword_ids), ("semantic", semantic_ids)]:
        print(f"\n== {name} ==")
        by_kind: dict[str, list[int | None]] = {}
        for q in positives:
            by_kind.setdefault(q["kind"], []).append(rank_of(q["expected"], fn(q["query"])))
        for kind, ranks in by_kind.items():
            r1 = sum(r == 1 for r in ranks) / len(ranks)
            r3 = sum(r is not None for r in ranks) / len(ranks)
            mrr = sum(1 / r for r in ranks if r) / len(ranks)
            print(f"{kind:11} n={len(ranks):2}  recall@1={r1:.2f}  recall@3={r3:.2f}  MRR={mrr:.2f}")

    print("\n== semantic top-1 cosine score, by kind (for MIN_SCORE) ==")
    by_kind_scores: dict[str, list[float]] = {}
    for q in QUERIES:
        by_kind_scores.setdefault(q["kind"], []).append(retrieval.score_all(q["query"])[0][0])
    for kind, scores in by_kind_scores.items():
        print(f"{kind:11} min={min(scores):.3f}  max={max(scores):.3f}")

    print(f"\n== at MIN_SCORE={retrieval.MIN_SCORE} ==")
    pos_kept = sum(bool(retrieval.search(q["query"])) for q in positives)
    negs = [q for q in QUERIES if not q["expected"]]
    neg_empty = sum(not retrieval.search(q["query"]) for q in negs)
    print(f"positives with >=1 hit: {pos_kept}/{len(positives)}")
    print(f"no_match correctly empty: {neg_empty}/{len(negs)}")
    for q in negs:
        top = retrieval.score_all(q["query"])[0]
        print(f"  {top[0]:.3f} {top[1]['id']}  <- {q['query']}")


if __name__ == "__main__":
    main()
