from typing import Annotated, Optional, TypedDict


def _add_messages(left: list[dict], right: list[dict]) -> list[dict]:
    """Simple append reducer — no LangChain dependency."""
    return left + right


class Hypothesis(TypedDict):
    signal: str   # "strong" | "adequate" | "weak" | "unknown"
    confidence: float  # 0.0 – 1.0
    notes: str


class JudgeVerdict(TypedDict):
    verdict: str            # "accept" | "flag"
    critique: str           # 1-2 sentence explanation
    adjusted_score: Optional[int]  # populated only when verdict="flag"


class AnswerRecord(TypedDict):
    question: str
    answer: str
    evaluation: dict        # score, signals, gaps (from Haiku)
    judge_verdict: Optional[JudgeVerdict]  # adversarial critique (from Sonnet); None for mock/ollama


class InterviewState(TypedDict):
    messages: Annotated[list[dict], _add_messages]   # Anthropic format dicts
    candidate: dict                                   # name, background, role
    hypotheses: dict[str, Hypothesis]                 # per-competency model
    answers: list[AnswerRecord]                       # full Q&A history
    questions_remaining: int                          # countdown from 10
    interview_complete: bool                          # set by end_interview tool
    model_tier: str                                   # "mock"|"ollama"|"haiku"|"sonnet"
    debrief: Optional[str]                            # final report, set at end
    cv_text: str                                      # parsed CV plain text (cacheable)
    jd_text: str                                      # parsed JD plain text (cacheable)
    policy_context: str                               # RAG-retrieved hiring policy snippets (scope+sensitivity filtered)


def initial_state(
    candidate: dict,
    model_tier: str,
    cv_text: str = "",
    jd_text: str = "",
    policy_context: str = "",
) -> InterviewState:
    return InterviewState(
        messages=[],
        candidate=candidate,
        hypotheses={
            "leadership":         {"signal": "unknown", "confidence": 0.0, "notes": ""},
            "technical_depth":    {"signal": "unknown", "confidence": 0.0, "notes": ""},
            "agentic_systems":    {"signal": "unknown", "confidence": 0.0, "notes": ""},
            "customer_empathy":   {"signal": "unknown", "confidence": 0.0, "notes": ""},
            "strategic_thinking": {"signal": "unknown", "confidence": 0.0, "notes": ""},
        },
        answers=[],
        questions_remaining=10,
        interview_complete=False,
        model_tier=model_tier,
        debrief=None,
        cv_text=cv_text,
        jd_text=jd_text,
        policy_context=policy_context,
    )
