"""Clearance-based sensitivity filtering.

Documents carry a sensitivity level; personas carry a clearance level.
A document is readable only when its sensitivity does not exceed the
persona's clearance. This mirrors standard enterprise access-control models
(e.g. public < confidential < restricted).

The interviewer persona is hardcoded at "confidential" clearance, meaning:
  - public documents  → allowed
  - confidential docs → allowed
  - restricted docs   → blocked

Keeping clearance logic here (not in the retriever) means the retriever stays
simple and this module can be unit-tested independently.
"""

from typing import TypedDict

from app.context.internal_docs import PolicyDocument


# Ordered clearance levels: higher integer = higher sensitivity
CLEARANCE_LEVELS: dict[str, int] = {
    "public": 0,
    "confidential": 1,
    "restricted": 2,
}


class Persona(TypedDict):
    name: str
    clearance: str  # "public" | "confidential" | "restricted"


# The AI interviewer persona. Confidential clearance gives it access to
# evaluation standards and the competency framework, but not approval thresholds.
INTERVIEWER_PERSONA: Persona = {
    "name": "interviewer",
    "clearance": "confidential",
}


def filter_by_sensitivity(
    docs: list[PolicyDocument],
    persona: Persona,
) -> list[PolicyDocument]:
    """Return only the documents the persona is cleared to read.

    Args:
        docs: Candidate documents (already scope-filtered by the retriever).
        persona: The persona requesting access; must have a 'clearance' key.

    Returns:
        Documents whose sensitivity level <= persona's clearance level.
    """
    persona_level = CLEARANCE_LEVELS.get(persona["clearance"], 0)
    return [
        doc for doc in docs
        if CLEARANCE_LEVELS.get(doc["sensitivity"], 0) <= persona_level
    ]
