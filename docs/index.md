# Documentation Index — PersonaGraph

This directory contains modular technical documentation. Each file covers one subsystem in depth. CLAUDE.md in the repo root holds the quick-reference architecture summary; these docs hold the detail.

## Files

| File | What it covers |
|------|---------------|
| [architecture.md](architecture.md) | System design, rationale, and key decisions |
| [agent.md](agent.md) | LangGraph graph, state, nodes, tools, and prompts |
| [api.md](api.md) | FastAPI endpoints, SSE streaming, session lifecycle |
| [frontend.md](frontend.md) | React components, SSE client hook, CSS design system |
| [model-routing.md](model-routing.md) | Per-task model selection, adapters, prompt caching |
| [sse-events.md](sse-events.md) | Complete SSE event contract between backend and frontend |
| [testing-phases.md](testing-phases.md) | Mock → Ollama → Haiku → Sonnet phased test strategy |
| [architecture-review.md](architecture-review.md) | Enterprise-readiness review: strengths, gaps, production recommendations |
| [task.md](task.md) | Session task log — completed and outstanding work |

## Quick orientation

```
PersonaGraph/
├── agent/          ← LangGraph graph + tools + prompts  →  docs/agent.md
├── api/            ← FastAPI + SSE routes               →  docs/api.md
├── frontend/src/   ← React + Vite chat UI               →  docs/frontend.md
├── scripts/        ← headless test scripts (Options 1-3 quality checks)
├── docs/           ← this directory
├── CLAUDE.md       ← architecture summary for Claude Code
└── pyproject.toml  ← Python deps (anthropic, langgraph, fastapi)
```

## Test scripts (`scripts/`)

Standalone quality-verification scripts. Run from repo root with `uv run python scripts/<name>.py`.

| Script | Purpose |
|--------|---------|
| `score_calibration.py` | Compares Haiku vs Sonnet on `evaluate_answer` for weak/adequate/strong answers. Asserts scores within ±1. |
| `headless_runner.py` | Shared async driver — invokes the LangGraph directly with predefined answers; no FastAPI or SSE required. |
| `hypothesis_trace.py` | 5-turn session with escalating quality; prints hypothesis evolution table and checks coherence. |
| `adversarial_test.py` | Bad-answer session; checks scores ≤ 5, gaps present, judge flags, session completes. |

## Running the app

```bash
# Backend (from repo root)
MODEL_TIER=mock PYTHONPATH=. py -3 -m uvicorn api.main:app --reload

# Frontend (separate terminal)
cd frontend && npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api` → `http://localhost:8000`.
