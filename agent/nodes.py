"""
LangGraph node implementations.

Nodes are async functions: (InterviewState, config) → dict of state updates.
Events are emitted to an asyncio.Queue passed via config["configurable"]["event_queue"].
The SSE route reads from this queue and streams to the client.
"""

import asyncio
import json
import os
import time
from typing import Any

import anthropic
from langgraph.types import RunnableConfig

from agent.models import get_adapter, get_anthropic_model, log_api_usage
from agent.prompts import build_system_prompt, build_static_prompt, build_dynamic_prompt
from agent.state import InterviewState
from agent.tools import TOOL_REGISTRY, TOOL_SCHEMAS, judge_evaluation
from api.logging_config import get_logger

_logger = get_logger()


# ---------------------------------------------------------------------------
# Event emission helper
# ---------------------------------------------------------------------------

async def _emit(queue: asyncio.Queue | None, event: dict) -> None:
    if queue is not None:
        await queue.put(event)


_CACHE_MIN_CHARS = 2048 * 4  # ~2048 tokens; 1 token ≈ 4 chars (conservative estimate)


def _should_cache(text: str) -> bool:
    """Return True if text is long enough to meet the Sonnet/Haiku 2048-token cache minimum."""
    return len(text) >= _CACHE_MIN_CHARS



# ---------------------------------------------------------------------------
# interviewer_node
# ---------------------------------------------------------------------------

async def interviewer_node(state: InterviewState, config: RunnableConfig | None = None) -> dict:
    """
    Core reasoning node. Runs the Sonnet interviewer with extended thinking and all 4 tools.
    For mock/ollama tiers, delegates to the adapter. For haiku/sonnet, calls Anthropic natively.
    """
    config = config or {}
    configurable = config.get("configurable") or {}
    queue: asyncio.Queue | None = configurable.get("event_queue")
    session_id: str | None = configurable.get("session_id")
    tier = state["model_tier"]
    system = build_system_prompt(state)

    adapter = get_adapter(tier)
    if adapter:
        # Mock or Ollama — no real Anthropic call
        await _emit(queue, {
            "type": "thinking",
            "content": f"[{tier.upper()}] Deciding interview strategy...",
        })
        if hasattr(adapter, "complete_messages"):
            message = adapter.complete_messages(
                messages=state["messages"],
                system=system,
                tools=TOOL_SCHEMAS,
            )
        else:
            message = {
                "role": "assistant",
                "content": [{"type": "text", "text": "[adapter missing complete_messages]"}],
            }

        content = message.get("content", [])
        has_tool_calls = any(
            isinstance(b, dict) and b.get("type") == "tool_use" for b in content
        )

        if has_tool_calls:
            # Mock path — emit tool_call events
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    await _emit(queue, {
                        "type": "tool_call",
                        "name": block["name"],
                        "input": block["input"],
                    })
            return {"messages": [message]}

        # Plain text path (Ollama) — treat response as the interview question
        text = next(
            (b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"),
            "",
        )
        remaining = state["questions_remaining"] - 1
        await _emit(queue, {
            "type": "question",
            "content": text,
            "meta": {"questions_remaining": remaining},
        })
        return {"messages": [message], "questions_remaining": remaining}

    # --- Real Anthropic path (haiku/sonnet) ---
    model = get_anthropic_model("interviewer")
    client = anthropic.Anthropic()

    # Build kwargs; extended thinking only for sonnet tier (haiku doesn't support it)
    # System prompt split into two blocks: static (JD + CV + invariant instructions, cached)
    # and dynamic (hypotheses, history — changes each turn, not cached).
    # cache_control is only set when the static block meets the 2048-token minimum.
    static_text = build_static_prompt(state["cv_text"], state["jd_text"], state.get("policy_context", ""))
    static_block: dict[str, Any] = {"type": "text", "text": static_text}
    if _should_cache(static_text):
        static_block["cache_control"] = {"type": "ephemeral"}

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": 8000,
        "tools": TOOL_SCHEMAS,
        "system": [
            static_block,
            {
                "type": "text",
                "text": build_dynamic_prompt(state),  # hypotheses, history — changes each turn
            },
        ],
        # Anthropic requires at least one message; seed first turn if empty.
        "messages": state["messages"] or [{"role": "user", "content": "Begin the interview."}],
    }
    if tier == "sonnet":
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": 5000}

    # Stream the response and emit events
    content_blocks: list[dict] = []
    stream_start = time.perf_counter()

    with client.messages.stream(**kwargs) as stream:
        current_block: dict | None = None

        for event in stream:
            event_type = event.type

            if event_type == "content_block_start":
                block = event.content_block
                current_block = {"type": block.type}
                if block.type == "thinking":
                    current_block["thinking"] = ""
                elif block.type == "text":
                    current_block["text"] = ""
                elif block.type == "tool_use":
                    current_block.update({
                        "id": block.id,
                        "name": block.name,
                        "input_json": "",
                    })

            elif event_type == "content_block_delta":
                delta = event.delta
                if current_block is None:
                    continue
                if delta.type == "thinking_delta":
                    current_block["thinking"] = current_block.get("thinking", "") + delta.thinking
                    await _emit(queue, {
                        "type": "thinking_delta",
                        "content": delta.thinking,
                    })
                elif delta.type == "signature_delta":
                    current_block["signature"] = current_block.get("signature", "") + delta.signature
                elif delta.type == "text_delta":
                    current_block["text"] = current_block.get("text", "") + delta.text
                elif delta.type == "input_json_delta":
                    current_block["input_json"] = (
                        current_block.get("input_json", "") + delta.partial_json
                    )

            elif event_type == "content_block_stop":
                if current_block is None:
                    continue

                btype = current_block["type"]
                if btype == "thinking":
                    content_blocks.append({
                        "type": "thinking",
                        "thinking": current_block["thinking"],
                        "signature": current_block.get("signature", ""),
                    })
                elif btype == "text":
                    content_blocks.append({"type": "text", "text": current_block["text"]})
                elif btype == "tool_use":
                    raw_json = current_block.get("input_json", "{}")
                    try:
                        tool_input = json.loads(raw_json)
                    except json.JSONDecodeError:
                        tool_input = {}
                    block_dict = {
                        "type": "tool_use",
                        "id": current_block["id"],
                        "name": current_block["name"],
                        "input": tool_input,
                    }
                    content_blocks.append(block_dict)
                    await _emit(queue, {
                        "type": "tool_call",
                        "name": current_block["name"],
                        "input": tool_input,
                    })
                current_block = None

        # Pull final usage stats (includes cache_read / cache_creation counts)
        final_message = stream.get_final_message()

    log_api_usage(
        node="interviewer",
        model=model,
        usage=final_message.usage,
        duration_ms=(time.perf_counter() - stream_start) * 1000,
        session_id=session_id,
        turn_number=len(state["answers"]) + 1,
        extra={"questions_remaining": state["questions_remaining"]},
    )

    message = {"role": "assistant", "content": content_blocks}
    return {"messages": [message]}


# ---------------------------------------------------------------------------
# tool_node
# ---------------------------------------------------------------------------

async def tool_node(state: InterviewState, config: RunnableConfig | None = None) -> dict:
    """
    Dispatches tool calls from the last assistant message.
    Applies side effects to state (hypotheses, interview_complete, answers, questions_remaining).
    """
    config = config or {}
    configurable = config.get("configurable") or {}
    queue: asyncio.Queue | None = configurable.get("event_queue")
    session_id: str | None = configurable.get("session_id")
    tier = state["model_tier"]

    last_message = state["messages"][-1]
    content = last_message.get("content", [])
    if isinstance(content, str):
        content = []

    tool_results: list[dict] = []
    state_updates: dict[str, Any] = {}

    # Track the last question generated this turn for answer records
    last_generated_question: str | None = None

    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue

        tool_name = block["name"]
        tool_input = block.get("input", {})
        tool_id = block["id"]

        fn = TOOL_REGISTRY.get(tool_name)
        if fn is None:
            result: Any = {"error": f"Unknown tool: {tool_name}"}
        else:
            result = fn(**tool_input, model_tier=tier)

        # --- State side-effects ---
        if tool_name == "update_hypotheses":
            state_updates["hypotheses"] = result
            _logger.info("hypotheses_updated", extra={
                "session_id": session_id,
                "turn": len(state["answers"]) + 1,
                "hypotheses": {
                    k: {"signal": v["signal"], "confidence": v["confidence"]}
                    for k, v in result.items() if isinstance(v, dict)
                },
            })

        elif tool_name == "evaluate_answer":
            question = tool_input.get("question", "")
            answer = tool_input.get("answer", "")

            # Judge first 3 answers unconditionally (fairness baseline) and any
            # low-confidence evaluation (Haiku uncertain → Sonnet spot-check).
            answer_index = len(state["answers"])
            should_judge = answer_index < 3 or result.get("confidence") == "low"
            verdict = judge_evaluation(question, answer, result, model_tier=tier) if should_judge else None
            if verdict is not None:
                await _emit(queue, {
                    "type": "judge_verdict",
                    "verdict": verdict.get("verdict"),
                    "critique": verdict.get("critique"),
                    "adjusted_score": verdict.get("adjusted_score"),
                    "tool_use_id": tool_id,
                })

            new_answers = list(state["answers"]) + [{
                "question": question,
                "answer": answer,
                "evaluation": result,
                "judge_verdict": verdict,
            }]
            state_updates["answers"] = new_answers
            _logger.info("evaluation_result", extra={
                "session_id": session_id,
                "turn": len(state["answers"]) + 1,
                "score": result.get("score"),
                "signals": result.get("signals"),
                "gaps": result.get("gaps"),
                "confidence_eval": result.get("confidence"),
                "judge_verdict": verdict.get("verdict") if verdict else None,
                "judge_adjusted_score": verdict.get("adjusted_score") if verdict else None,
            })

        elif tool_name == "generate_question":
            # Decrement remaining count; store the question text for SSE
            remaining = state["questions_remaining"] - 1
            state_updates["questions_remaining"] = remaining
            last_generated_question = result if isinstance(result, str) else str(result)
            await _emit(queue, {
                "type": "question",
                "content": last_generated_question,
                "meta": {
                    "category": tool_input.get("category"),
                    "depth": tool_input.get("depth"),
                    "questions_remaining": remaining,
                },
            })
            _logger.info("question_generated", extra={
                "session_id": session_id,
                "turn": len(state["answers"]) + 1,
                "category": tool_input.get("category"),
                "depth": tool_input.get("depth"),
                "questions_remaining": remaining,
            })

        elif tool_name == "end_interview":
            state_updates["interview_complete"] = True

        # Emit tool result event
        await _emit(queue, {
            "type": "tool_result",
            "name": tool_name,
            "output": result,
        })

        # For evaluate_answer, nest evaluation + judge_verdict so the interviewer sees both
        if tool_name == "evaluate_answer":
            tool_result_content = json.dumps({
                "evaluation": result,
                "judge_verdict": verdict,  # noqa: F821 — set in the evaluate_answer branch above
            })
        else:
            tool_result_content = json.dumps(result)

        tool_results.append({
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": tool_result_content,
        })

    # Append tool results as a user message (Anthropic multi-turn format)
    tool_message = {"role": "user", "content": tool_results}
    return {"messages": [tool_message], **state_updates}


# ---------------------------------------------------------------------------
# debrief_node
# ---------------------------------------------------------------------------

async def debrief_node(state: InterviewState, config: RunnableConfig | None = None) -> dict:
    """Generates a final assessment report. Runs once after interview_complete is set."""
    config = config or {}
    queue: asyncio.Queue | None = (config.get("configurable") or {}).get("event_queue")
    tier = state["model_tier"]

    await _emit(queue, {"type": "debrief_start"})

    adapter = get_adapter(tier)
    if adapter:
        debrief_text = (
            "[Mock Debrief]\n\n"
            "**Overall Assessment:** The candidate demonstrated adequate leadership framing "
            "with clear room to test technical depth and agentic systems knowledge.\n\n"
            "**Strengths:** Structured thinking, leadership presence.\n"
            "**Gaps:** Technical specificity, quantified outcomes.\n"
            "**Recommendation:** Proceed to technical deep-dive round."
        )
        await _emit(queue, {"type": "debrief", "content": debrief_text})
        await _emit(queue, {"type": "done"})
        return {"debrief": debrief_text}

    # Build debrief prompt
    qa_parts = []
    for r in state["answers"]:
        entry = f"Q: {r['question']}\nA: {r['answer']}\nEval (Haiku): {json.dumps(r['evaluation'])}"
        verdict = r.get("judge_verdict")
        if verdict:
            entry += f"\nJudge (Sonnet): verdict={verdict['verdict']}, critique={verdict['critique']}"
            if verdict.get("adjusted_score") is not None:
                entry += f", adjusted_score={verdict['adjusted_score']}"
        qa_parts.append(entry)
    qa_summary = "\n\n".join(qa_parts)
    hyp_summary = json.dumps(state["hypotheses"], indent=2)

    prompt = (
        "You conducted an interview for the role described in the job specification.\n\n"
        f"CANDIDATE: {state['candidate'].get('name', 'Candidate')}\n\n"
        f"FINAL HYPOTHESES:\n{hyp_summary}\n\n"
        f"INTERVIEW TRANSCRIPT:\n{qa_summary}\n\n"
        "Write a concise hiring assessment (300–400 words) covering:\n"
        "1. Overall readiness signal\n"
        "2. Top 2-3 strengths with evidence\n"
        "3. Top 2-3 gaps or risks\n"
        "4. Recommendation (strong hire / hire / hold / no hire)\n"
        "5. Suggested next steps if progressing"
    )

    from agent.models import call_text
    debrief_text = call_text(prompt, model=get_anthropic_model("debrief"), max_tokens=768)

    await _emit(queue, {"type": "debrief", "content": debrief_text})
    await _emit(queue, {"type": "done"})
    return {"debrief": debrief_text}
