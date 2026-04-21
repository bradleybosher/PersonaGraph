# CLAUDE.md

## When to read docs
- Touching agent/: read docs/agent.md
- Touching api/: read docs/api.md  
- Touching frontend/: read docs/frontend.md
- New to this codebase: read docs/index.md first

When modifying any file, read docs/DOCS_PROTOCOL.md before closing the task.

## Project Overview

PersonaGraph is an AI-powered interview preparation tool and exploration project for enterprise agentic systems patterns using LangGraph and the native Anthropic SDK. Input any CV and job description URL; the system conducts a structured mock interview, evaluates answers, and generates a debrief report.

## Core rule: LangGraph + native Anthropic SDK — no LangChain

LangGraph handles graph orchestration. `anthropic.Anthropic()` is called directly inside nodes. LangChain's `ChatAnthropic` wrapper hides extended thinking, prompt caching, and native `tool_use` — all deliberately visible here.

## Running locally

```bash
# Backend (from repo root)
.venv\scripts\activate
 cd api && uv run uvicorn main:app --reload

# Frontend (separate terminal)
cd frontend && npm run dev
# → http://localhost:5173
```