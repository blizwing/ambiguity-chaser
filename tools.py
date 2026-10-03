"""
Tools the agent can call. Plain Python, deliberately separate from graph.py
so they can be tested without an LLM. Week 11 uses keyword overlap for
search; embeddings are Week 12's job, so this is intentionally dumb.
"""

import json
import re

import retrieval

with open("test_corpus.json", mode="r", encoding="utf-8") as f:
    TEST_CORPUS = json.load(f)

CORPUS_IDS = {tc["id"] for tc in TEST_CORPUS}

# Words that appear in nearly every requirement/test case and would
# otherwise create matches on nothing meaningful.
STOPWORDS = {
    "the", "a", "an", "of", "to", "and", "or", "is", "are", "be", "in", "on",
    "for", "with", "that", "this", "it", "as", "by", "at", "from", "should",
    "must", "will", "can", "verify", "system", "user", "users",
}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower())) - STOPWORDS


def keyword_search(query: str) -> list[dict]:
    """Week 11 keyword-overlap search, kept as the baseline that
    evals/retrieval_eval.py measures embeddings against."""
    query_words = _words(query)
    scored = []
    for tc in TEST_CORPUS:
        overlap = len(query_words & _words(tc["title"] + " " + tc["description"]))
        if overlap > 0:
            scored.append((overlap, tc))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [tc for _, tc in scored[:3]]


def search_test_cases(query: str) -> list[dict]:
    """Semantic search (Week 12). Empty list = nothing similar enough.
    Raises retrieval.RetrievalError if retrieval itself is broken; callers
    must not treat that as 'no match'."""
    return retrieval.search(query)


SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_test_cases",
        "description": "Search the existing test case library by keywords. Returns up to 3 test cases (id, title, description) that share words with the query, or an empty list if none do.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords describing the behaviour the requirement asks for, e.g. 'account lockout failed login attempts'."
                }
            },
            "required": ["query"]
        }
    }
}
