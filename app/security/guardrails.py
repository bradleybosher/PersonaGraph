"""Input guardrails: detect prompt injection and data exfiltration attempts.

Runs on every candidate answer before the LangGraph graph is invoked.
If an attempt is detected, the API returns a safe refusal and skips the graph
entirely — the LLM is never exposed to the malicious input.

Three threat categories are screened:
  1. Financial data requests — attempts to extract confidential financial info
  2. Prompt injection — "ignore instructions", jailbreak patterns, etc.
  3. Restricted access probing — direct requests for classified documents

Design note: regex-based screening is lightweight and deterministic, which
makes it auditable and interview-explainable. A production system would layer
this with an LLM-based policy classifier for higher recall on novel phrasings.
"""

import re
from typing import TypedDict


class GuardrailResult(TypedDict):
    flagged: bool
    reason: str | None        # human-readable reason for logging
    safe_response: str | None # response to return to the user when flagged


_SAFE_REPLY = (
    "I'm here to conduct your interview and can only discuss topics relevant "
    "to your candidacy. I'm not able to help with that request."
)

# Each group is (category_label, list_of_patterns)
_THREAT_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "financial data request",
        [
            r"financ",           # financial, finance, financing
            r"revenue",
            r"budget",
            r"\bprofit\b",
            r"salary.{0,10}range",
            r"compensation.{0,10}band",
            r"share.{0,10}buyback",
            r"ebitda",
        ],
    ),
    (
        "prompt injection attempt",
        [
            r"ignore\s+(previous|above|all|prior)\s+instructions",
            r"disregard\s+(your|the|all)\s+(previous|prior|above|instructions)",
            r"forget\s+(everything|all|your\s+instructions)",
            r"jailbreak",
            r"system\s+prompt",
            r"you\s+are\s+now\s+(?:a\s+)?(?:an?\s+)?\w+",  # "you are now a DAN"
            r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions",
            r"pretend\s+you\s+are",
        ],
    ),
    (
        "restricted document access attempt",
        [
            r"restricted\s+document",
            r"confidential\s+document",
            r"internal\s+policy",
            r"show\s+me\s+the\s+policy",
            r"what\s+does\s+the\s+policy\s+say",
            r"access\s+(?:the\s+)?(?:restricted|confidential|internal)",
        ],
    ),
]


def detect_exfiltration_attempt(user_input: str) -> GuardrailResult:
    """Screen *user_input* for prompt injection or data exfiltration patterns.

    Args:
        user_input: The candidate's raw answer text.

    Returns:
        GuardrailResult with flagged=True and a safe_response when a threat
        pattern matches; flagged=False otherwise.
    """
    text = user_input.lower()

    for category, patterns in _THREAT_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text):
                return GuardrailResult(
                    flagged=True,
                    reason=f"{category} — matched pattern: {pattern!r}",
                    safe_response=_SAFE_REPLY,
                )

    return GuardrailResult(flagged=False, reason=None, safe_response=None)
