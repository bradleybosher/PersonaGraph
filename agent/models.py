"""
Model routing and adapters.

Design: get_model() returns a model identifier string for a given task and tier.
Callers (tools, nodes) use this to select between Anthropic models or adapters.

Routing table (per-task, not per-role):
  question_gen → sonnet   (user-facing; quality matters)
  evaluation   → haiku    (structured scoring; pattern match)
  sub-calls in update_hypotheses / end_interview → no model (LLM provides value directly)

For mock/ollama tiers, adapters intercept before any Anthropic API call.
"""

import json
import os
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

import anthropic
import httpx

from api.logging_config import get_logger

_logger = get_logger()


def log_api_usage(
    *,
    node: str,
    model: str,
    usage: Any,
    duration_ms: float,
    session_id: str | None = None,
    turn_number: int | None = None,
    extra: dict | None = None,
) -> None:
    """Emit a structured log for one Anthropic API call.

    Pulls input/output/cache-* token counts off the SDK's Usage object and
    computes a cache_hit_ratio so a downstream grep or dashboard can see at a
    glance whether prompt caching is landing.
    """
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
    input_tok = getattr(usage, "input_tokens", 0) or 0
    output_tok = getattr(usage, "output_tokens", 0) or 0
    total_input = input_tok + cache_read + cache_create
    hit_ratio = (cache_read / total_input) if total_input else 0.0

    payload = {
        "session_id": session_id,
        "node": node,
        "model": model,
        "input_tokens": input_tok,
        "output_tokens": output_tok,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_create,
        "cache_hit_ratio": round(hit_ratio, 3),
        "duration_ms": round(duration_ms, 1),
        "turn_number": turn_number,
    }
    if extra:
        payload.update(extra)
    _logger.info("anthropic_api_call", extra=payload)

# ---------------------------------------------------------------------------
# Model identifiers
# ---------------------------------------------------------------------------

_ANTHROPIC_MODELS = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
}

_TASK_MODEL_TIER: dict[str, str] = {
    "question_gen": "sonnet",
    "evaluation":   "haiku",
    "judge":        "sonnet",  # always Sonnet — judge must outrank evaluator regardless of session tier
    "debrief":      "sonnet",
    "interviewer":  "sonnet",
}


def get_anthropic_model(task: str) -> str:
    """Return the Anthropic model ID for a task (ignores mock/ollama — callers handle those).

    Always uses the per-task routing in _TASK_MODEL_TIER. The session tier (haiku/sonnet)
    only affects whether extended thinking is enabled in interviewer_node — not model selection.
    """
    tier_key = _TASK_MODEL_TIER.get(task, "haiku")
    return _ANTHROPIC_MODELS[tier_key]


# ---------------------------------------------------------------------------
# Mock adapter
# ---------------------------------------------------------------------------

class MockAdapter:
    """Returns hardcoded valid responses. Zero API calls. Used in MODEL_TIER=mock."""

    RESPONSES: dict[str, Any] = {
        "generate_question": (
            "Tell me about a time you led a technical team through significant ambiguity. "
            "What was the situation, and how did you decide what to do?"
        ),
        "evaluate_answer": {
            "score": 7,
            "signals": ["structured thinking", "leadership presence", "customer focus"],
            "gaps": ["specificity on outcomes", "metrics not mentioned"],
            "confidence": "medium",
            "summary": "Candidate demonstrates solid leadership framing but lacks quantified impact.",
        },
        "update_hypotheses": {
            "leadership":         {"signal": "adequate", "confidence": 0.6, "notes": "Shows structure; needs depth"},
            "technical_depth":    {"signal": "unknown",  "confidence": 0.0, "notes": "Not yet tested"},
            "agentic_systems":    {"signal": "unknown",  "confidence": 0.0, "notes": "Not yet tested"},
            "customer_empathy":   {"signal": "adequate", "confidence": 0.5, "notes": "Mentioned customer impact"},
            "strategic_thinking": {"signal": "unknown",  "confidence": 0.0, "notes": "Not yet tested"},
        },
        "end_interview": {
            "acknowledged": True,
            "rationale": "[Mock] Interview complete.",
        },
    }

    def complete(self, tool_name: str, **_kwargs: Any) -> Any:
        return self.RESPONSES.get(tool_name, {})

    def complete_messages(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        **_kwargs: Any,
    ) -> dict:
        """Simulate an interviewer response. On the first turn, just generate a question.
        On subsequent turns, evaluate the answer first, then generate the next question."""
        # Determine if there's a prior candidate answer (non-first turn)
        has_prior_answer = any(
            msg.get("role") == "user"
            and isinstance(msg.get("content"), str)
            for msg in messages
        )

        if not has_prior_answer:
            # Opening turn
            return {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": (
                            "[Mock thinking] The candidate has no answers yet. "
                            "I'll start with a leadership question to establish a baseline."
                        ),
                        "signature": "mock_sig",
                    },
                    {
                        "type": "tool_use",
                        "id": "mock_tool_001",
                        "name": "generate_question",
                        "input": {
                            "category": "leadership",
                            "depth": "surface",
                            "rationale": "Establish baseline — first question of the interview.",
                        },
                    },
                ],
            }

        # Follow-up turn: evaluate + generate
        # Find the most recent user answer string
        last_answer = ""
        last_question = "Tell me about a time you led a technical team through ambiguity."
        for msg in reversed(messages):
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                last_answer = msg["content"]
                break

        return {
            "role": "assistant",
            "content": [
                {
                    "type": "thinking",
                    "thinking": (
                        "[Mock thinking] The candidate answered the previous question. "
                        "I'll evaluate the response and decide on the next area to probe."
                    ),
                    "signature": "mock_sig",
                },
                {
                    "type": "tool_use",
                    "id": "mock_tool_002",
                    "name": "evaluate_answer",
                    "input": {
                        "question": last_question,
                        "answer": last_answer,
                    },
                },
                {
                    "type": "tool_use",
                    "id": "mock_tool_003",
                    "name": "generate_question",
                    "input": {
                        "category": "technical_depth",
                        "depth": "probe",
                        "rationale": "Probe technical depth after leadership baseline.",
                    },
                },
            ],
        }


# ---------------------------------------------------------------------------
# Ollama adapter (interviewer node only — NOT tool_use, see CLAUDE.md)
# ---------------------------------------------------------------------------

class OllamaAdapter:
    """Calls local llama3.2:3b for SSE/UI streaming tests. Does not handle tool_use."""

    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = "llama3.2:3b"

    def complete_messages(
        self,
        messages: list[dict],
        system: str,
        **_kwargs: Any,
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}]
            + [
                {"role": m["role"], "content": _flatten_content(m["content"])}
                for m in messages
                if m["role"] in ("user", "assistant")
            ],
            "stream": False,
        }
        resp = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=60)
        resp.raise_for_status()
        text = resp.json()["message"]["content"]
        return {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        }


# ---------------------------------------------------------------------------
# Anthropic caller helpers
# ---------------------------------------------------------------------------

def call_structured(
    prompt: str,
    output_schema: dict,
    model: str = "claude-haiku-4-5-20251001",
) -> dict:
    """
    Call Claude with tool_choice=forced to get structured JSON output.
    Used by evaluate_answer tool (Haiku) and debrief_node (Sonnet).
    """
    client = anthropic.Anthropic()
    start = time.perf_counter()
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        tools=[
            {
                "name": "structured_output",
                "description": "Return the requested structured data.",
                "input_schema": output_schema,
            }
        ],
        tool_choice={"type": "tool", "name": "structured_output"},
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_usage(
        node="call_structured",
        model=model,
        usage=response.usage,
        duration_ms=(time.perf_counter() - start) * 1000,
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    return {}


def call_text(prompt: str, model: str = "claude-sonnet-4-6", max_tokens: int = 512) -> str:
    """Plain text completion — used by generate_question tool and debrief_node."""
    client = anthropic.Anthropic()
    start = time.perf_counter()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    log_api_usage(
        node="call_text",
        model=model,
        usage=response.usage,
        duration_ms=(time.perf_counter() - start) * 1000,
    )
    for block in response.content:
        if hasattr(block, "text"):
            return block.text
    return ""


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------

_mock_adapter: MockAdapter | None = None
_ollama_adapter: OllamaAdapter | None = None


def get_adapter(tier: str) -> MockAdapter | OllamaAdapter | None:
    global _mock_adapter, _ollama_adapter
    if tier == "mock":
        if _mock_adapter is None:
            _mock_adapter = MockAdapter()
        return _mock_adapter
    if tier == "ollama":
        if _ollama_adapter is None:
            _ollama_adapter = OllamaAdapter()
        return _ollama_adapter
    return None  # real Anthropic tiers


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _flatten_content(content: str | list) -> str:
    """Collapse Anthropic content blocks to a plain string (for Ollama)."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block["text"])
            elif block.get("type") == "tool_result":
                parts.append(f"[tool_result] {block.get('content', '')}")
            elif block.get("type") == "tool_use":
                parts.append(f"[tool_call: {block['name']}] {json.dumps(block['input'])}")
    return "\n".join(parts)
