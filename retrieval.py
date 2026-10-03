"""
Semantic search over the test-case corpus (Week 12). Replaces Week 11's
keyword overlap as the engine behind `search_test_cases`.

Local embedding model via fastembed (ONNX, no API key, no data leaves the
machine, deterministic for a given model version). DeepSeek has no
embeddings endpoint, so a local model is the only option that doesn't add
a second vendor.
"""

import json

import numpy as np

MODEL_NAME = "BAAI/bge-small-en-v1.5"
# bge models are trained with this prefix on the *query* side only;
# documents are embedded as-is. Skipping it measurably weakens retrieval.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Cosine floor below which a hit is treated as "nothing similar". Picked
# from evals/retrieval_eval.py's score distributions, not guessed; re-run
# it if the model or corpus changes.
MIN_SCORE = 0.60


class RetrievalError(Exception):
    """The retrieval machinery itself failed (model load, corpus, empty
    index). Distinct from an empty result, which means 'nothing similar'.
    Week 11 carry-over: only the empty result is safe to treat as 'not
    covered'."""


_model = None
_index: np.ndarray | None = None
_corpus: list[dict] | None = None


def _doc_text(tc: dict) -> str:
    return f"{tc['title']}. {tc['description']}"


def _load_corpus() -> list[dict]:
    try:
        with open("test_corpus.json", mode="r", encoding="utf-8") as f:
            corpus = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise RetrievalError(f"could not load test_corpus.json: {e}") from e
    if not corpus:
        raise RetrievalError("test corpus is empty")
    return corpus


def _ensure_index() -> None:
    global _model, _index, _corpus
    if _index is not None:
        return
    try:
        from fastembed import TextEmbedding

        corpus = _load_corpus()
        model = TextEmbedding(MODEL_NAME)
        vectors = np.array(list(model.embed([_doc_text(tc) for tc in corpus])))
    except RetrievalError:
        raise
    except Exception as e:
        raise RetrievalError(f"could not build embedding index: {e}") from e
    # Normalise once so a dot product is cosine similarity.
    _index = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    _model, _corpus = model, corpus


def score_all(query: str) -> list[tuple[float, dict]]:
    """Every corpus entry with its cosine score, best first. Used by the
    eval script; search() is the thresholded view of this."""
    _ensure_index()
    try:
        q = np.array(next(iter(_model.embed([QUERY_PREFIX + query]))))
    except Exception as e:
        raise RetrievalError(f"could not embed query: {e}") from e
    q = q / np.linalg.norm(q)
    scores = _index @ q
    order = np.argsort(-scores)
    return [(float(scores[i]), _corpus[i]) for i in order]


def search(query: str, k: int = 3, min_score: float = MIN_SCORE) -> list[dict]:
    """Top-k entries scoring at least min_score, each with a `score` field.
    Empty list = nothing similar. Raises RetrievalError if broken."""
    return [
        {**tc, "score": round(s, 3)}
        for s, tc in score_all(query)[:k]
        if s >= min_score
    ]
