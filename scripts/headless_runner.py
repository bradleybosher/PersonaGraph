"""
Shared headless session driver for Options 2 and 3.

Drives a full interview with predefined answers without FastAPI or SSE.
Imports the compiled LangGraph directly and invokes it turn by turn.
"""
import asyncio
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from agent.graph import interview_graph
from agent.state import initial_state

_SAMPLE_CV = """
Brad Bosher — Engineering Leader
15 years in software engineering and technical leadership.
Currently: Director of Solutions Architecture at a SaaS company.
Previous: Senior SA Manager, Principal Engineer at cloud infrastructure firms.
Built and led teams of 10-20 engineers and SAs across EMEA.
Deep experience with distributed systems, cloud architecture (AWS/GCP), and AI/ML integration.
Key projects: migrated 3M-user platform to microservices; deployed LLM-powered internal tooling.
"""

_SAMPLE_JD = """
Manager of Solutions Architects — Anthropic
Lead a team of Solutions Architects helping enterprise customers adopt Claude API.
Requirements: 8+ years technical leadership, experience with LLM/AI products,
strong customer empathy, ability to influence product roadmap from field signal.
Responsibilities: hire and develop SAs, own technical win rate, partner with AE teams,
drive agentic systems adoption, represent customer needs to product.
"""


async def run_session(
    answers: list[str],
    model_tier: str = "sonnet",
    cv_text: str = _SAMPLE_CV,
    jd_text: str = _SAMPLE_JD,
    verbose: bool = True,
    min_turns: int = 1,
) -> tuple[dict, list[dict]]:
    """Drive a full interview with predefined answers.

    Returns (final_state, snapshots) where each snapshot covers one turn:
    {turn, question, answer, hypotheses, evaluation, judge_verdict}.
    """
    state: dict = initial_state(
        candidate={
            "name": "Test Candidate",
            "background": "Engineering leader with 15 years experience",
            "current_role": "Director of Solutions Architecture",
        },
        model_tier=model_tier,
        cv_text=cv_text,
        jd_text=jd_text,
    )

    queue: asyncio.Queue = asyncio.Queue()
    config = {
        "configurable": {
            "event_queue": queue,
            "session_id": f"headless-{model_tier}",
        }
    }
    snapshots: list[dict] = []

    for turn, answer in enumerate(answers, start=1):
        if verbose:
            print(f"  [turn {turn}] invoking graph...", flush=True)

        state = await interview_graph.ainvoke(state, config=config)

        # Drain all events emitted during this graph run
        events: list[dict] = []
        while not queue.empty():
            events.append(queue.get_nowait())

        question = next(
            (e["content"] for e in events if e.get("type") == "question"),
            None,
        )
        evaluation = next(
            (e["output"] for e in events if e.get("type") == "tool_result" and e.get("name") == "evaluate_answer"),
            None,
        )
        judge = next(
            (e for e in events if e.get("type") == "judge_verdict"),
            None,
        )

        snapshots.append({
            "turn": turn,
            "question": question,
            "answer": answer,
            "hypotheses": {
                k: {"signal": v["signal"], "confidence": v["confidence"]}
                for k, v in state.get("hypotheses", {}).items()
            },
            "evaluation": evaluation,
            "judge_verdict": judge.get("verdict") if judge else None,
        })

        if state.get("interview_complete") or state.get("debrief"):
            if turn >= min_turns:
                if verbose:
                    print(f"  [session ended at turn {turn}]")
                break
            # Suppress early termination until min_turns is reached
            if verbose:
                print(f"  [turn {turn}: early end suppressed (min_turns={min_turns})]")
            state = dict(state)
            state["interview_complete"] = False
            state["debrief"] = None

        # Inject predefined answer for next turn
        state = dict(state)
        state["messages"] = list(state["messages"]) + [
            {"role": "user", "content": answer}
        ]

    # Run final debrief turn if not yet complete
    if not state.get("debrief"):
        if verbose:
            print("  [running debrief...]", flush=True)
        state = await interview_graph.ainvoke(state, config=config)

    return state, snapshots
