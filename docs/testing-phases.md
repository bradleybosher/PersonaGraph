# Testing Phases

Each phase has a clear goal and a pass criterion before moving to the next. The tiers are controlled by the `MODEL_TIER` environment variable.

## Phase 1 — Architecture (`mock`)

**Goal:** Full graph wired, SSE streaming end-to-end, UI renders. Zero API calls.

**Start:**
```bash
MODEL_TIER=mock PYTHONPATH=. py -3 -m uvicorn api.main:app --reload --port 8000
cd frontend && npm run dev
```

**Pass criteria:**
- `POST /api/session` returns SSE stream ending with `done`
- Session completes 1 question per `ainvoke()` call
- `questions_remaining` decrements correctly each turn
- `answers` list grows on each answer submission
- React renders: thinking panel, tool badges, question bubbles, candidate bubbles
- Thinking panel collapses/expands correctly
- Tool badges show ✓ after result arrives
- No TypeScript errors (`npx tsc --noEmit`)

**Smoke test (Python):**
```bash
MODEL_TIER=mock PYTHONPATH=. py -3 -c "
import asyncio, os
os.environ['MODEL_TIER'] = 'mock'
from agent.graph import build_graph
from agent.state import initial_state

async def run():
    graph = build_graph()
    candidate = {'name': 'Test', 'background': 'SA', 'current_role': 'SA'}
    state = initial_state(candidate, 'mock')
    r = await graph.ainvoke(state, config={'configurable': {'event_queue': None}})
    assert r['questions_remaining'] == 9, f'Expected 9, got {r[\"questions_remaining\"]}'
    print('Phase 1 PASSED')

asyncio.run(run())
"
```

**Status:** ✅ Complete. HTTP smoke test verified. TypeScript clean.

---

## Phase 2 — Streaming/UI (`ollama`)

**Goal:** Confirm SSE rendering with a live model that has real streaming latency. No API cost.

**Prerequisite:** Ollama running locally with `llama3.2:3b` pulled.
```bash
ollama pull llama3.2:3b
ollama serve
```

**Start:**
```bash
MODEL_TIER=ollama PYTHONPATH=. py -3 -m uvicorn api.main:app --reload
```

**What to test:**
- Thinking panel appears and streams content with visible latency (tests async rendering)
- Tool badges appear and fill in as results arrive
- Auto-scroll works as messages arrive over time
- Input is disabled during streaming and re-enabled after `done`
- No layout shift or flicker between events

**What to expect:** Ollama with `llama3.2:3b` does NOT call tools — it returns plain text. Tool badges will not appear. The interviewer node treats the plain text response as the question, emits a `question` SSE event, and the graph pauses for the candidate's answer. Q&A cycles correctly until `questions_remaining` reaches 0, then the mock debrief fires. The goal is testing SSE pipe latency and UI rendering, not tool_use correctness.

**Status:** ⏳ Not yet validated. Requires Ollama installed.

---

## Phase 3 — Quality (`haiku`)

**Goal:** Real LLM calls. Validate prompt quality, evaluation accuracy, hypothesis coherence, and judge calibration.

**Start:**
```bash
ANTHROPIC_API_KEY=sk-... MODEL_TIER=haiku PYTHONPATH=. py -3 -m uvicorn api.main:app --reload
```

**What to test:**
- Questions are relevant, well-formed, and probe the stated competency
- `evaluate_answer` scores are calibrated (7-8 for strong answers, 4-5 for weak)
- `judge_verdict` events appear in the SSE stream after each `evaluate_answer`
- Judge `verdict` field is `"accept"` or `"flag"` — never null or malformed
- When judge flags, `adjusted_score` is present and differs from Haiku's raw score
- Hypotheses update meaningfully across turns
- The interviewer adapts depth based on answer quality
- Debrief covers all 5 competencies with evidence and references judge verdicts where flagged

**Target cost:** ~$0.02 per session (Haiku eval + Sonnet judge per answer).

**Run 5+ sessions** with varied answer quality before moving to Phase 4.

**Status:** ⏳ Not yet run.

---

## Phase 4 — Polish (`sonnet`)

**Goal:** Full extended thinking, debrief quality, real strategic adaptation.

**Start:**
```bash
ANTHROPIC_API_KEY=sk-... MODEL_TIER=sonnet PYTHONPATH=. py -3 -m uvicorn api.main:app --reload
```

**What to test:**
- Extended thinking appears in the panel with substantive reasoning
- Interviewer adapts strategy mid-session (shifts category, probes deeper, ends early)
- Questions in `deep_dive` depth are genuinely challenging
- Debrief is specific, evidence-based, and actionable
- Prompt caching is working (check Anthropic usage dashboard for cache read tokens by turn 5)
- Interviewer visibly uses judge verdict in thinking (look for reasoning about adjusted scores)
- Judge `flag` rate is reasonable — not flagging everything, not rubber-stamping everything

**Target cost:** ~$0.10 per session.

**Status:** ⏳ Not yet run.

---

## MVP routing

Production target: Haiku for evaluation tools, Sonnet for interviewer and question generation.

```bash
ANTHROPIC_API_KEY=sk-... MODEL_TIER=sonnet PYTHONPATH=. py -3 -m uvicorn api.main:app
```

The `sonnet` tier already uses this routing (Haiku for `evaluate_answer`, Sonnet for judge + everything else). No additional configuration needed.

**Target cost:** ~$0.05–0.10 per session with prompt caching active (judge adds one Sonnet call per answer).

---

## Graph visualization

```python
from agent.graph import interview_graph
print(interview_graph.get_graph().draw_mermaid())
```

Paste output into [mermaid.live](https://mermaid.live) to render the graph topology.
