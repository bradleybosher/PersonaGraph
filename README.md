# PersonaGraph

An AI-powered interview practice tool built to explore enterprise agentic systems patterns with LangGraph and the native Anthropic SDK. Upload a CV and a job description URL; the system conducts a structured mock interview, evaluates answers in real time, and generates a detailed debrief report.

## Why this project exists

Interview coaching is a natural domain for exploring LLM orchestration: it requires multi-turn conversation, structured evaluation, tool use, streaming, and cost management — the same capabilities that appear in enterprise AI deployments. This project was built to get hands-on with those patterns at a level of depth that a wrapper library would obscure.

## Architecture highlights

### Native Anthropic SDK — no LangChain

`anthropic.Anthropic()` is called directly inside every node. LangChain's `ChatAnthropic` abstraction hides three features that matter in production:

- **Prompt caching** — `cache_control: ephemeral` on individual system blocks, not the whole prompt
- **Extended thinking** — `thinking` content blocks streamed live to the UI
- **Native tool_use format** — tool calls and results match exactly what appears in the Anthropic Console

### LangGraph orchestration

The interviewer agent has all four tools available simultaneously with no forced call order. LangGraph conditional edges are driven entirely by what the LLM returned — not by a predetermined sequence. The graph decides whether to evaluate, update its mental model, ask another question, or end the interview.

```
interviewer → tool_executor → interviewer (loop)
                   ↓
              debrief (on end_interview)
```

### Per-task model routing

| Task | Model | Rationale |
|------|-------|-----------|
| Interviewer orchestration | Sonnet + extended thinking | Non-deterministic strategy |
| `generate_question` | Sonnet | User-facing output quality |
| `evaluate_answer` | Haiku | Structured scoring; 5–10× cheaper |
| `judge_evaluation` | Sonnet (always) | Judge must outrank evaluator |
| `update_hypotheses` | No sub-model | LLM provides update via tool call |
| Debrief | Sonnet | Final report quality |

Routing by task rather than by role reduces cost by ~5–10× over a single-model baseline for the evaluation workload.

### LLM-as-judge

After Haiku scores each answer, a Sonnet judge adversarially reviews the evaluation before it influences the interviewer's hypothesis updates. Four checks: signal accuracy, gap fairness, score calibration, confidence validity. If the judge flags a material flaw, the adjusted score takes precedence. Every evaluation has a paired critique stored in state and visible in the debrief.

### Prompt caching with keep-alive

CV and job description sit in a cached system block (~2–4k tokens). A 5-minute keep-alive loop refreshes the ephemeral cache TTL while the candidate is composing. Without this, a 6-minute pause silently evicts the cache and doubles input-token cost for the rest of the session. Every API call logs `cache_read_input_tokens` and `cache_hit_ratio` so caching is verifiable, not assumed.

### Phased testing tiers

| Tier | Purpose | Cost |
|------|---------|------|
| `mock` | Graph, state, SSE wiring — zero API calls | $0 |
| `ollama` | SSE rendering with a live stream (llama3.2:3b) | $0 |
| `haiku` | Prompt quality and evaluation accuracy | ~$0.01/session |
| `sonnet` | Extended thinking, full debrief experience | ~$0.10/session |

The `MODEL_TIER` environment variable is a single switch that changes the entire model routing. Most demos cannot test their graphs without burning credits; this one can.

## Stack

| Layer | Technology |
|-------|-----------|
| Agent graph | LangGraph 0.2+ |
| LLM calls | Anthropic SDK (native) |
| Backend | FastAPI + SSE via `StreamingResponse` |
| Frontend | React + Vite, custom SSE client |
| Config | `MODEL_TIER` env var |

## Project structure

```
agent/
  graph.py        # LangGraph graph definition and conditional edges
  nodes.py        # Node implementations (interviewer, tool_executor, debrief)
  tools.py        # Tool implementations + Anthropic tool schemas
  prompts.py      # Static/dynamic prompt split for caching
  models.py       # Per-task model routing and adapter pattern
  state.py        # InterviewState TypedDict

api/
  main.py         # FastAPI app
  routes.py       # /session and /session/{id}/answer endpoints
  keepalive.py    # Cache keep-alive loop
  logging_config.py

frontend/src/
  App.tsx         # Root, routing between intake and chat
  IntakeForm.tsx  # CV upload + JD URL → candidate profile
  ChatView.tsx    # SSE-connected chat interface
  ThinkingPanel.tsx  # Collapsible extended thinking display
  useInterview.ts # Custom hook: session state + SSE streaming
```

## Getting started

**Prerequisites:** Python 3.11+, Node 18+, `uv`, an Anthropic API key (required for `haiku`/`sonnet` tiers).

```bash
# Clone and set up environment
git clone https://github.com/your-username/PersonaGraph
cd PersonaGraph
cp .env.example .env   # add ANTHROPIC_API_KEY

# Backend
python -m venv .venv
.venv/scripts/activate          # Windows
# source .venv/bin/activate     # macOS/Linux
cd api && uv run uvicorn main:app --reload

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

Start with `MODEL_TIER=mock` (default) to verify the graph and streaming work before making API calls.

## Enterprise readiness notes

The [`docs/architecture-review.md`](docs/architecture-review.md) document covers what works now versus what would change before a real customer deployment: session persistence, auth/tenancy, rate limiting, per-session cost caps, PII handling, and prompt injection defences. The current implementation is deliberately scoped as a demo; the review doc is the honest accounting of the gap.
