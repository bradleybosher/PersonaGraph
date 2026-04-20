"""Internal document store for the interview system.

Each document carries two access-control fields:
  - scope: "interview_system" | "corporate"
      Controls which pipeline can retrieve the document.
      Only scope="interview_system" documents are ever retrievable by the
      interview RAG pipeline. Corporate documents exist in the same store but
      are structurally excluded at retrieval time.
  - sensitivity: "public" | "confidential" | "restricted"
      Controls which personas can read the document once retrieved.
      Filtered against the persona's clearance level before prompt injection.
"""

from typing import TypedDict


class PolicyDocument(TypedDict):
    title: str
    text: str
    scope: str        # "interview_system" | "corporate"
    sensitivity: str  # "public" | "confidential" | "restricted"


# ---------------------------------------------------------------------------
# Document store
# ---------------------------------------------------------------------------

ALL_DOCS: list[PolicyDocument] = [
    # --- Interview system documents (retrievable by the pipeline) ---
    {
        "title": "Interview Evaluation Standards",
        "scope": "interview_system",
        "sensitivity": "public",
        "text": (
            "All interviews must assess candidates against five core competencies: "
            "leadership, technical depth, agentic systems knowledge, customer empathy, "
            "and strategic thinking. Each competency should be probed with at least one "
            "behavioural question (STAR format) and one technical or situational question. "
            "Scores are assigned on a 1–10 scale. A score of 7 or above signals a strong "
            "hire recommendation for that competency. Interviewers must not share numeric "
            "scores with candidates during the session."
        ),
    },
    {
        "title": "Competency Framework for Technical Roles",
        "scope": "interview_system",
        "sensitivity": "confidential",
        "text": (
            "Technical hiring managers are expected to probe depth, not surface familiarity. "
            "For agentic systems roles, candidates should demonstrate understanding of: "
            "LLM tool use patterns, multi-agent orchestration trade-offs, prompt caching "
            "economics, and production observability requirements. "
            "For leadership competencies, look for evidence of cross-functional influence "
            "without authority, and decisions made under ambiguity with limited data. "
            "Calibration note: a candidate who scores 8+ on all competencies in a single "
            "session warrants a second-opinion review before proceeding to offer."
        ),
    },
    {
        "title": "Hiring Approval Thresholds",
        "scope": "interview_system",
        "sensitivity": "restricted",
        "text": (
            "Offers above Band 7 require VP-level sign-off before extension. "
            "Any deviation from the published salary band requires written justification "
            "submitted to Total Rewards within 48 hours of verbal offer. "
            "Relocation packages exceeding the standard allowance must be approved by "
            "the Regional HR Director. This document is restricted to hiring managers "
            "and HR business partners only."
        ),
    },

    # --- Corporate document (must NEVER be retrieved by the interview pipeline) ---
    {
        "title": "Q3 Financial Performance Report",
        "scope": "corporate",
        "sensitivity": "restricted",
        "text": (
            "Q3 revenue came in at $142M, representing 18% YoY growth. EBITDA margin "
            "improved to 22% driven by infrastructure cost reductions. The board has "
            "approved a $50M share buyback programme commencing Q4. Headcount targets "
            "for the next fiscal year are under review pending finalisation of the "
            "annual operating plan. This document is classified as restricted and must "
            "not be shared outside the executive leadership team."
        ),
    },
]
