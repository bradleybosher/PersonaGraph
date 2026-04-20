"""RAG-lite retriever with hard scope enforcement.

Design constraints:
  1. Scope gate — only documents where scope == "interview_system" are ever
     considered. Corporate documents are excluded before any keyword matching,
     so they cannot appear in results regardless of query content.
  2. Keyword matching — simple token overlap; no vector DB required. Sufficient
     for a small, curated policy document set where exact terminology matters.
  3. No sensitivity filtering here — that is the responsibility of
     app.security.sensitivity.filter_by_sensitivity, applied after retrieval.
     Keeping the two concerns separate makes each step independently testable.
"""

import re

from app.context.internal_docs import PolicyDocument


def retrieve_policy_context(
    query: str,
    documents: list[PolicyDocument],
) -> list[PolicyDocument]:
    """Return documents relevant to *query*, restricted to scope='interview_system'.

    Args:
        query: Free-text query derived from CV + JD content.
        documents: The full document store (may contain corporate docs).

    Returns:
        Subset of documents that (a) have scope='interview_system' and
        (b) share at least one non-trivial keyword with the query.
        If no documents match on keywords, all in-scope documents are returned
        as a fallback so the interviewer always has policy context available.
    """
    # --- Step 1: Hard scope gate ---
    # Corporate documents are excluded here, unconditionally.
    in_scope = [d for d in documents if d["scope"] == "interview_system"]

    # --- Step 2: Keyword extraction ---
    # Strip punctuation, lowercase, remove short stop-words.
    _STOP = {"a", "an", "the", "and", "or", "of", "in", "to", "for", "is", "are",
             "be", "was", "were", "by", "at", "on", "with", "this", "that", "it"}
    tokens = {
        t for t in re.split(r"\W+", query.lower()) if len(t) > 3 and t not in _STOP
    }

    if not tokens:
        return in_scope  # No usable query tokens — return all in-scope docs

    # --- Step 3: Match ---
    matched = [
        doc for doc in in_scope
        if tokens & set(re.split(r"\W+", (doc["title"] + " " + doc["text"]).lower()))
    ]

    # Fallback: return all in-scope docs if nothing matched keyword-wise
    return matched if matched else in_scope
