"""
REST + SSE routes.

POST /api/session          — create session, run first interviewer turn, stream events
POST /api/session/{id}/answer — submit candidate answer, run next graph turn, stream events
GET  /api/session/{id}     — return current session state (for reconnect)
"""

import asyncio
import io
import json
import os
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore[assignment,misc]

from agent.graph import interview_graph
from agent.state import InterviewState, initial_state
from api.keepalive import cancel_keepalive, schedule_keepalive

router = APIRouter()

# In-memory session store (sufficient for demo)
_sessions: dict[str, InterviewState] = {}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CandidateProfile(BaseModel):
    name: str
    background: str
    current_role: str


class CreateSessionRequest(BaseModel):
    candidate: CandidateProfile
    model_tier: str = "mock"
    cv_text: str = ""
    jd_text: str = ""


class AnswerRequest(BaseModel):
    answer: str


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def _run_and_stream(
    session_id: str,
    state: InterviewState,
    user_message: dict | None = None,
) -> AsyncGenerator[str]:
    """
    Run one graph turn, streaming events from nodes via asyncio.Queue.
    Updates the session store with the resulting state when done.
    """
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    # Cancel any outstanding keep-alive before running the turn so its ping
    # does not race with the interviewer's own API call.
    cancel_keepalive(session_id)

    if user_message:
        # Append user's answer to the message history before invoking
        state = dict(state)  # shallow copy
        state["messages"] = list(state["messages"]) + [user_message]

    async def _invoke() -> None:
        try:
            result = await interview_graph.ainvoke(
                state,
                config={"configurable": {"event_queue": queue, "session_id": session_id}},
            )
            _sessions[session_id] = result
            # Reschedule keep-alive while waiting for the next candidate answer.
            if not result.get("interview_complete"):
                schedule_keepalive(session_id, result)
        except Exception as exc:
            await queue.put({"type": "error", "message": str(exc)})
        finally:
            await queue.put(None)  # sentinel

    task = asyncio.create_task(_invoke())

    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield _sse(event)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_pdf_text(data: bytes) -> str:
    """Extract plain text from PDF bytes using pypdf."""
    if PdfReader is None:
        raise HTTPException(status_code=500, detail="pypdf not installed")
    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages)
    # Collapse excessive blank lines
    return re.sub(r"\n{3,}", "\n\n", text).strip()


async def _fetch_url_text(url: str) -> str:
    """Fetch a URL and return visible text, stripping HTML tags."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        try:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        except httpx.RequestError as exc:
            raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}") from exc
    if resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"URL returned HTTP {resp.status_code}",
        )
    soup = BeautifulSoup(resp.text, "html.parser")
    # Remove script/style noise
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    # Prefer <main> or <article> if present, else fall back to <body>
    container = soup.find("main") or soup.find("article") or soup.body or soup
    text = container.get_text(separator="\n")
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/parse")
async def parse_documents(
    cv_file: UploadFile = File(...),
    jd_url: str = Form(...),
) -> dict[str, str]:
    """
    Parse a CV PDF and job description URL into plain text.

    Returns { cv_text, jd_text } for use in /api/session.
    """
    # Parse PDF
    pdf_bytes = await cv_file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="cv_file is empty")
    try:
        cv_text = _extract_pdf_text(pdf_bytes)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {exc}") from exc

    # Fetch and clean JD
    jd_text = await _fetch_url_text(jd_url)

    return {"cv_text": cv_text, "jd_text": jd_text}


@router.post("/session")
async def create_session(body: CreateSessionRequest) -> StreamingResponse:
    """
    Create a new interview session and immediately run the first graph turn
    (interviewer generates opening question). Streams SSE events.
    """
    session_id = str(uuid.uuid4())
    tier = body.model_tier or os.getenv("MODEL_TIER", "mock")

    state = initial_state(
        candidate=body.candidate.model_dump(),
        model_tier=tier,
        cv_text=body.cv_text,
        jd_text=body.jd_text,
    )
    _sessions[session_id] = state

    async def generate() -> AsyncGenerator[str]:
        # First event: session metadata
        yield _sse({"type": "session_created", "session_id": session_id, "model_tier": tier})
        async for chunk in _run_and_stream(session_id, state):
            yield chunk

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/session/{session_id}/answer")
async def submit_answer(session_id: str, body: AnswerRequest) -> StreamingResponse:
    """Submit a candidate answer and run the next graph turn. Streams SSE events."""
    state = _sessions.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if state.get("interview_complete"):
        raise HTTPException(status_code=400, detail="Interview already complete")

    user_message = {"role": "user", "content": body.answer}

    async def generate() -> AsyncGenerator[str]:
        async for chunk in _run_and_stream(session_id, state, user_message=user_message):
            yield chunk

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/session/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    """Return current session state for reconnect/debug."""
    state = _sessions.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "questions_remaining": state["questions_remaining"],
        "interview_complete": state["interview_complete"],
        "answers_count": len(state["answers"]),
        "model_tier": state["model_tier"],
        "hypotheses": state["hypotheses"],
        "debrief": state.get("debrief"),
    }
