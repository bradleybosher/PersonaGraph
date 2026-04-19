"""Per-session cache keep-alive.

The Anthropic ephemeral prompt cache has a 5-minute TTL. If a candidate pauses
longer than that between turns, the cached static block (JD + CV, ~2–4k tokens)
is evicted and the next turn pays full input-token price.

While a session is paused waiting for the candidate's next answer, we fire a
tiny `messages.create` every CACHE_KEEPALIVE_SECONDS (default 240s = 4m) that
reuses the exact same cached system block with `max_tokens=1`. The call is a
pure cache read — cost is ~1 output token — and resets the 5-minute timer.

Skipped for mock/ollama tiers (no remote cache to preserve).
Capped at KEEPALIVE_MAX_PINGS per session to bound runaway cost if a client
tab closes without disconnecting the SSE stream.
"""

import asyncio
import os
import time

import anthropic

from agent.models import get_anthropic_model, log_api_usage
from agent.prompts import build_static_prompt
from agent.state import InterviewState
from api.logging_config import get_logger

_logger = get_logger()

KEEPALIVE_INTERVAL = int(os.getenv("CACHE_KEEPALIVE_SECONDS", "240"))
KEEPALIVE_MAX_PINGS = int(os.getenv("CACHE_KEEPALIVE_MAX_PINGS", "12"))

_tasks: dict[str, asyncio.Task] = {}
_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


async def _ping_loop(session_id: str, state: InterviewState) -> None:
    tier = state["model_tier"]
    model = get_anthropic_model("interviewer")
    static_text = build_static_prompt(state["cv_text"], state["jd_text"])
    client = _get_client()

    pings = 0
    while pings < KEEPALIVE_MAX_PINGS:
        try:
            await asyncio.sleep(KEEPALIVE_INTERVAL)
        except asyncio.CancelledError:
            return

        pings += 1
        start = time.perf_counter()
        try:
            # Only ping if the static block is large enough to have been cached (2048-token min).
            if len(static_text) < 2048 * 4:
                return
            response = await client.messages.create(
                model=model,
                max_tokens=1,
                system=[
                    {
                        "type": "text",
                        "text": static_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": "ping"}],
            )
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "cache_keepalive_error",
                extra={"session_id": session_id, "ping": pings, "error": str(exc)},
            )
            continue

        log_api_usage(
            node="cache_keepalive",
            model=model,
            usage=response.usage,
            duration_ms=(time.perf_counter() - start) * 1000,
            session_id=session_id,
            extra={"ping_number": pings},
        )

    _logger.info(
        "cache_keepalive_cap_reached",
        extra={"session_id": session_id, "max_pings": KEEPALIVE_MAX_PINGS},
    )


def schedule_keepalive(session_id: str, state: InterviewState) -> None:
    """Start (or restart) a keep-alive loop for this session.

    No-op for mock/ollama tiers. Cancels any existing loop for this session
    before starting a new one so the interval clock resets on each turn.
    """
    if state["model_tier"] not in ("haiku", "sonnet"):
        return
    if state.get("interview_complete"):
        return

    cancel_keepalive(session_id)
    task = asyncio.create_task(_ping_loop(session_id, state))
    _tasks[session_id] = task
    _logger.info(
        "cache_keepalive_scheduled",
        extra={
            "session_id": session_id,
            "interval_seconds": KEEPALIVE_INTERVAL,
            "max_pings": KEEPALIVE_MAX_PINGS,
        },
    )


def cancel_keepalive(session_id: str) -> None:
    task = _tasks.pop(session_id, None)
    if task is not None and not task.done():
        task.cancel()
