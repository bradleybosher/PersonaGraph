"""
Tool implementations and Anthropic tool schemas.

Four tools given to the interviewer simultaneously — no forced call order.
Model routing:
  generate_question → Sonnet (quality matters; user-facing output)
  evaluate_answer   → Haiku (structured scoring; fast)
  update_hypotheses → no sub-model (LLM provides update directly via extended thinking)
  end_interview     → no sub-model (signals state change only)
"""

import json
from agent.models import MockAdapter, call_structured, call_text, get_adapter, get_anthropic_model
from agent.prompts import build_judge_prompt

# ---------------------------------------------------------------------------
# Anthropic tool schemas (native format — not LangChain)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "evaluate_answer",
        "description": (
            "Objectively evaluate the candidate's answer using a structured rubric. "
            "Always call this after receiving an answer before updating hypotheses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The exact question that was asked"},
                "answer":   {"type": "string", "description": "The candidate's verbatim answer"},
            },
            "required": ["question", "answer"],
        },
    },
    {
        "name": "update_hypotheses",
        "description": (
            "Store your updated mental model of the candidate after evaluating an answer. "
            "Provide the full hypotheses dict — it replaces the previous one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hypotheses": {
                    "type": "object",
                    "description": "Updated hypotheses keyed by competency name",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "signal":     {"type": "string", "enum": ["strong", "adequate", "weak", "unknown"]},
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "notes":      {"type": "string"},
                        },
                        "required": ["signal", "confidence", "notes"],
                    },
                }
            },
            "required": ["hypotheses"],
        },
    },
    {
        "name": "generate_question",
        "description": (
            "Generate the next interview question. "
            "Call this when you've decided to continue the interview."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Competency area to probe",
                    "enum": ["leadership", "technical_depth", "agentic_systems", "customer_empathy", "strategic_thinking"],
                },
                "depth": {
                    "type": "string",
                    "enum": ["surface", "probe", "deep_dive"],
                    "description": "surface=opener, probe=follow-up, deep_dive=stress test",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this category and depth given what you know so far",
                },
            },
            "required": ["category", "depth", "rationale"],
        },
    },
    {
        "name": "end_interview",
        "description": (
            "End the interview. Use this instead of generate_question when you have "
            "sufficient signal to form an assessment. Do not call both in one turn."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rationale": {
                    "type": "string",
                    "description": "Why you're ending now — which hypotheses are settled",
                },
            },
            "required": ["rationale"],
        },
        "cache_control": {"type": "ephemeral"},  # caches all 4 tool schemas as one prefix
    },
]

# ---------------------------------------------------------------------------
# Evaluation schema (used by Haiku structured call)
# ---------------------------------------------------------------------------

_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict":       {"type": "string", "enum": ["accept", "flag"]},
        "critique":      {"type": "string"},
        "adjusted_score": {
            "anyOf": [{"type": "integer", "minimum": 1, "maximum": 10}, {"type": "null"}]
        },
    },
    "required": ["verdict", "critique", "adjusted_score"],
}

_EVALUATION_SCHEMA = {
    "type": "object",
    "properties": {
        "score":      {"type": "integer", "minimum": 1, "maximum": 10},
        "signals":    {"type": "array", "items": {"type": "string"}},
        "gaps":       {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "summary":    {"type": "string"},
    },
    "required": ["score", "signals", "gaps", "confidence", "summary"],
}

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def evaluate_answer(question: str, answer: str, model_tier: str) -> dict:
    adapter = get_adapter(model_tier)
    if adapter:
        return adapter.complete("evaluate_answer", question=question, answer=answer)

    prompt = (
        "You are evaluating a candidate for the role described in the job specification.\n\n"
        f"Question asked: {question}\n\n"
        f"Candidate's answer: {answer}\n\n"
        "Score this answer on a 10-point scale. Identify specific positive signals and gaps. "
        "Be objective and specific — avoid vague praise."
    )
    return call_structured(prompt, _EVALUATION_SCHEMA, model=get_anthropic_model("evaluation"))


def judge_evaluation(question: str, answer: str, evaluation: dict, model_tier: str) -> dict | None:
    """Adversarially validate Haiku's evaluation using Sonnet.

    Returns None for mock/ollama tiers (no real LLM to judge).
    Always uses Sonnet regardless of session tier — the judge must outrank the evaluator.
    """
    if get_adapter(model_tier) is not None:
        return None  # skip for mock/ollama

    prompt = build_judge_prompt(question, answer, evaluation)
    # Deliberately do NOT pass model_tier so task routing picks "judge" → sonnet
    return call_structured(prompt, _JUDGE_SCHEMA, model=get_anthropic_model("judge"))


def update_hypotheses(hypotheses: dict | str, model_tier: str) -> dict:
    """No sub-model call — the interviewer LLM provides the update directly."""
    if isinstance(hypotheses, str):
        try:
            hypotheses = json.loads(hypotheses)
        except (json.JSONDecodeError, ValueError):
            return {}
    return hypotheses if isinstance(hypotheses, dict) else {}


def generate_question(category: str, depth: str, rationale: str, model_tier: str) -> str:
    adapter = get_adapter(model_tier)
    if adapter:
        return adapter.complete("generate_question")

    depth_guidance = {
        "surface":   "Ask a broad, opening question to establish a baseline.",
        "probe":     "Ask a targeted follow-up that digs into a specific aspect.",
        "deep_dive": "Ask a challenging scenario or stress-test their reasoning.",
    }
    prompt = (
        "You are interviewing a candidate for the role described in the job specification.\n\n"
        f"Competency to probe: {category}\n"
        f"Depth: {depth} — {depth_guidance.get(depth, '')}\n"
        f"Rationale: {rationale}\n\n"
        "Generate ONE precise, behavioural or situational interview question. "
        "Do not include preamble, explanation, or follow-up — just the question itself."
    )
    return call_text(prompt, model=get_anthropic_model("question_gen"))


def end_interview(rationale: str, model_tier: str) -> dict:
    """Signals the graph to move to debrief. No sub-model call."""
    return {"acknowledged": True, "rationale": rationale}


# ---------------------------------------------------------------------------
# Dispatch registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY = {
    "evaluate_answer":  evaluate_answer,
    "update_hypotheses": update_hypotheses,
    "generate_question": generate_question,
    "end_interview":     end_interview,
}
