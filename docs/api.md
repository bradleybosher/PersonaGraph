# API — FastAPI + SSE Routes

## App setup (`api/main.py`)

```python
load_dotenv()
configure_logging()   # JSON structured logs on stdout
app = FastAPI(title="PersonaGraph")
app.add_middleware(CORSMiddleware, allow_origins=[FRONTEND_ORIGIN])
app.include_router(router, prefix="/api")
```

`FRONTEND_ORIGIN` defaults to `http://localhost:5173` (Vite dev server). Set via env var for production.

`configure_logging()` (from `api/logging_config.py`) wires a single `interview_coach` logger that emits one JSON line per event on stdout. Every Anthropic API call logs `anthropic_api_call` with `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `cache_hit_ratio`, `duration_ms`, `node`, `model`, `session_id`, and `turn_number`.

## Endpoints

### `POST /api/session`

Creates a new session and immediately runs the first graph turn (interviewer generates opening question).

**Request body:**
```json
{
  "candidate": {"name": "...", "background": "...", "current_role": "..."},
  "model_tier": "mock"
}
```

**Response:** `text/event-stream` (SSE). First event is always `session_created`:
```
data: {"type": "session_created", "session_id": "<uuid>", "model_tier": "mock"}
```

Followed by graph events (thinking, tool_call, question, tool_result, done). See [sse-events.md](sse-events.md) for the full event contract.

**Session storage:** The resulting `InterviewState` is stored in `_sessions[session_id]` (in-memory dict).

---

### `POST /api/session/{session_id}/answer`

Submits a candidate answer and runs the next graph turn.

**Request body:**
```json
{"answer": "I led a cloud migration for 12 engineers..."}
```

**Response:** `text/event-stream`. No `session_created` event. Streams tool_call, question (or debrief), done.

Returns `400` if session is already complete, `404` if session not found.

---

### `GET /api/session/{session_id}`

Returns current session state for reconnect or debugging.

**Response:**
```json
{
  "session_id": "...",
  "questions_remaining": 8,
  "interview_complete": false,
  "answers_count": 2,
  "model_tier": "mock",
  "hypotheses": {...},
  "debrief": null
}
```

## Streaming implementation (`_run_and_stream`)

```
HTTP request
    │
    ▼
_run_and_stream(session_id, state, user_message?)
    │
    ├── asyncio.create_task(_invoke())   ← runs graph.ainvoke() in background
    │       │
    │       └── emits events to asyncio.Queue via config["configurable"]["event_queue"]
    │
    └── while True: queue.get() → yield _sse(event) → client
            │
            └── breaks on sentinel None (emitted by _invoke() when done)
```

The `asyncio.Queue` is the decoupling point between the graph (which runs in a background task) and the SSE generator (which yields to the HTTP response). This avoids blocking the event loop.

If the client disconnects, the `finally` block in `_run_and_stream` cancels the background task.

## Cache keep-alive (`api/keepalive.py`)

The Anthropic ephemeral prompt cache has a 5-minute TTL. After each turn completes and the graph pauses awaiting the candidate's next answer, `_run_and_stream` calls `schedule_keepalive(session_id, state)`. That starts a background `asyncio.Task` that fires a minimal `messages.create` (same cached system block, `max_tokens=1`) every `CACHE_KEEPALIVE_SECONDS` (default 240). The next `/answer` call cancels the loop before running the turn.

- No-op for `model_tier in ("mock", "ollama")` — no remote cache to preserve.
- Capped at `CACHE_KEEPALIVE_MAX_PINGS` (default 12) to bound cost if the client tab closes.
- Each ping logs as `anthropic_api_call` with `node="cache_keepalive"` — grep those to verify cache hits are still landing.

**`_sse(event)`** formats a dict as an SSE data line:
```python
f"data: {json.dumps(event)}\n\n"
```

## Session lifecycle

```
POST /session  →  session created, state stored, first Q streamed
    │
    ▼
POST /session/{id}/answer  →  state loaded, answer appended, next Q streamed, state updated
    │
    ▼  (repeat N times)
    │
    └── interview_complete = True OR questions_remaining = 0
            │
            ▼
        debrief streamed, done event sent
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MODEL_TIER` | `mock` | Controls model routing for all nodes |
| `ANTHROPIC_API_KEY` | — | Required for haiku/sonnet tiers |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS allowed origin |
| `API_HOST` | `127.0.0.1` | Uvicorn bind host |
| `API_PORT` | `8000` | Uvicorn bind port |
| `LOG_LEVEL` | `INFO` | Log level for the `interview_coach` JSON logger |
| `CACHE_KEEPALIVE_SECONDS` | `240` | Interval between cache-refresh pings (must be < 300s TTL) |
| `CACHE_KEEPALIVE_MAX_PINGS` | `12` | Ping cap per session (bounds idle-session cost) |
