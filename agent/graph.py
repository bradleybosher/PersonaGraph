"""
LangGraph StateGraph definition.

Topology:
  START → interviewer_node
            ├─[tool_calls present]──► tool_node ──► interviewer_node  (loop)
            └─[complete or no questions]──► debrief_node ──► END
"""

from langgraph.graph import END, StateGraph

from agent.nodes import debrief_node, interviewer_node, tool_node
from agent.state import InterviewState


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------

def _route_after_interviewer(state: InterviewState) -> str:
    """Conditional edge: inspect last message to decide next node."""
    messages = state.get("messages", [])
    if not messages:
        return END

    last = messages[-1]
    if last.get("role") != "assistant":
        return END

    content = last.get("content", [])
    has_tool_calls = any(
        isinstance(block, dict) and block.get("type") == "tool_use"
        for block in content
    )

    if has_tool_calls:
        return "tool_node"

    # No tool calls — check completion conditions first
    if state.get("interview_complete") or state.get("questions_remaining", 10) <= 0:
        return "debrief_node"

    # Plain text response (Ollama): pause graph, wait for candidate's answer
    has_text = any(
        isinstance(block, dict) and block.get("type") == "text"
        for block in content
    )
    if has_text:
        return END

    # Safety: no tool calls, no text, not complete — end cleanly
    return "debrief_node"


def _route_after_tools(state: InterviewState) -> str:
    """
    After tool execution:
    - If interview is complete or out of questions → debrief_node
    - If generate_question was just called → END (pause; wait for candidate's answer)
    - Otherwise → interviewer_node (more tool calls needed in this turn)
    """
    if state.get("interview_complete") or state.get("questions_remaining", 10) <= 0:
        return "debrief_node"

    # Check if a question was generated in the most recent tool pass.
    # The tool results message is the last; the assistant call is just before it.
    messages = state.get("messages", [])
    for msg in reversed(messages[:-1]):  # skip the last tool-results user message
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        generated_question = any(
            isinstance(b, dict)
            and b.get("type") == "tool_use"
            and b.get("name") == "generate_question"
            for b in content
        )
        if generated_question:
            return END  # pause graph; resume on next answer submission
        break  # only inspect the most recent assistant message

    return "interviewer_node"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    graph = StateGraph(InterviewState)

    graph.add_node("interviewer_node", interviewer_node)
    graph.add_node("tool_node", tool_node)
    graph.add_node("debrief_node", debrief_node)

    graph.set_entry_point("interviewer_node")

    graph.add_conditional_edges(
        "interviewer_node",
        _route_after_interviewer,
        {
            "tool_node":    "tool_node",
            "debrief_node": "debrief_node",
            END:            END,
        },
    )

    graph.add_conditional_edges(
        "tool_node",
        _route_after_tools,
        {
            "interviewer_node": "interviewer_node",
            "debrief_node":     "debrief_node",
            END:                END,
        },
    )

    graph.add_edge("debrief_node", END)

    return graph.compile()


# Singleton compiled graph
interview_graph = build_graph()
