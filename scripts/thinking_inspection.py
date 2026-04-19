"""
Extended thinking inspection — prints what Sonnet actually reasons about.

Runs a 3-turn headless session with model_tier="sonnet" and prints the raw
thinking blocks from each interviewer turn: what competency it picked, why it
probed where it did, how it weighted the evaluation result.

No assertions — the output is the evidence.

Usage:
    uv run python scripts/thinking_inspection.py
"""
import asyncio
import json
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent.graph import interview_graph
from agent.state import initial_state
from scripts.headless_runner import _SAMPLE_CV, _SAMPLE_JD

_SEP = "=" * 70

ANSWERS = [
    # Turn 1 — weak leadership: forces reasoning about how to probe further
    "I just figure it out as we go. Leadership is about instinct, not process.",
    # Turn 2 — strong technical: should shift signal, reasoning should reflect that
    (
        "At Salesforce I redesigned our RAG pipeline — switched from BM25 to hybrid "
        "dense/sparse retrieval, dropping p95 latency from 4s to 800ms. Biggest "
        "challenge was keeping the reranker calibrated as the doc corpus grew; I built "
        "a feedback loop that triggered nightly re-calibration on negative-rating events."
    ),
    # Turn 3 — adequate agentic: middling, should prompt probing
    "I've used LangChain agents for some internal tooling but haven't built one from scratch.",
]


def _print_thinking_blocks(messages: list, offset: int = 0) -> None:
    """Print thinking blocks from messages[offset:] only (new messages this turn)."""
    for msg in messages[offset:]:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue

        thinking_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "thinking"]
        text_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
        tool_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]

        if not thinking_blocks:
            continue

        for i, block in enumerate(thinking_blocks, start=1):
            print(f"\n[THINKING BLOCK {i}/{len(thinking_blocks)}]")
            print(block.get("thinking", "").strip())

        for block in text_blocks:
            text = block.get("text", "").strip()
            if text:
                print(f"\n[TEXT RESPONSE]\n{text}")

        for block in tool_blocks:
            name = block.get("name", "?")
            inp = block.get("input", {})
            print(f"\n[TOOL CALL: {name}]")
            print(f"input: {json.dumps(inp, indent=2)}")


async def main() -> int:
    state: dict = initial_state(
        candidate={
            "name": "Test Candidate",
            "background": "Engineering leader with 15 years experience",
            "current_role": "Director of Solutions Architecture",
        },
        model_tier="sonnet",
        cv_text=_SAMPLE_CV,
        jd_text=_SAMPLE_JD,
    )

    queue: asyncio.Queue = asyncio.Queue()
    config = {
        "configurable": {
            "event_queue": queue,
            "session_id": "headless-thinking-inspection",
        }
    }

    for turn, answer in enumerate(ANSWERS, start=1):
        print(f"\n{_SEP}")
        print(f"TURN {turn}")
        print(_SEP)

        msg_offset = len(state.get("messages", []))
        state = await interview_graph.ainvoke(state, config=config)

        # Drain queue to extract the question text for display
        events: list[dict] = []
        while not queue.empty():
            events.append(queue.get_nowait())

        question = next(
            (e["content"] for e in events if e.get("type") == "question"),
            "(question not captured)",
        )

        print(f"\nQUESTION: {question}")
        print(f"ANSWER:   {answer}")

        # Print only the thinking blocks produced during this turn (new messages only).
        _print_thinking_blocks(state.get("messages", []), offset=msg_offset)

        if state.get("interview_complete") or state.get("debrief"):
            print(f"\n  [session ended at turn {turn}]")
            break

        state = dict(state)
        state["messages"] = list(state["messages"]) + [
            {"role": "user", "content": answer}
        ]

    print(f"\n{_SEP}")
    print("INSPECTION COMPLETE")
    print(_SEP)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
