# PersonaGraph

A structured AI interview system built to surface the engineering patterns that matter in production LLM applications: cost-aware model routing, adversarial evaluation, structural data access control, and prompt caching under real constraints.

Users provide a CV and job description. The system conducts a 10-question interview across five competencies, evaluates answers via a two-tier Haiku-then-Sonnet judge layer, tracks evolving candidate hypotheses, and produces a hiring assessment. Built with the native Anthropic SDK (`anthropic.Anthropic()` directly, no LangChain) and LangGraph.

---

## System topology

```
START
  ↓
interviewer_node   (claude-sonnet-4-6 · extended thinking · 4 tools, no forced order)
  │
  ├─ [tool_use blocks present?]
  │     ↓
  │   tool_node ─┬─► [complete / exhausted] ──────────► debrief_node ──► END
  │              ├─► [generate_question called] ──────► END  (pause; await next answer)
  │              └─► interviewer_node  (more tool calls needed this turn)
  │
  └─ [complete OR questions_remaining == 0] ──────────► debrief_node ──► END
       [plain text, Ollama tier] ──────────────────────► END  (pause)
```

All 4 tools are given to the interviewer simultaneously. The LLM decides call order, whether to evaluate, and whether to end early:

| Tool | Sub-model | Side effect |
|---|---|---|
| `generate_question` | Sonnet | Emits SSE `question` event; decrements counter |
| `evaluate_answer` | Haiku | Structured 1–10 score; triggers judge layer |
| `update_hypotheses` | — | LLM provides delta directly; merged, not replaced |
| `end_interview` | — | State signal only; routes to debrief |

---

## Model routing

Session tier (`haiku` / `sonnet`) controls whether extended thinking is enabled — it does not change model selection. Every task always uses the same model.

| Task | Model | Reason |
|---|---|---|
| Interviewer strategy | `claude-sonnet-4-6` | Reasoning depth; extended thinking (sonnet tier) |
| Question generation | `claude-sonnet-4-6` | User-facing; quality matters |
| Answer evaluation | `claude-haiku-4-5-20251001` | Pattern-matching; 10× cheaper, acceptable accuracy |
| Judge (adversarial oversight) | `claude-sonnet-4-6` | Always Sonnet — judge must outrank evaluator |
| Debrief generation | `claude-sonnet-4-6` | Final user-facing report |

---

## Prompt caching

Each `interviewer_node` call splits the system prompt into two blocks:

```
System message:
┌──────────────────────────────────────────────────────┐
│ STATIC BLOCK           cache_control: ephemeral      │
│ CV text · JD text · invariant instructions           │
│ (applied when ≥ 2048 tokens; cache hit on turns 2+) │
├──────────────────────────────────────────────────────┤
│ DYNAMIC BLOCK          (no cache)                    │
│ 5 competency hypotheses · message history (≤ 30)    │
│ · RAG-retrieved policy context                       │
└──────────────────────────────────────────────────────┘
```

All 4 tool schemas are also cached as a single prefix via `cache_control: ephemeral` on the last entry.

Every API call logs `cache_read_input_tokens`, `cache_creation_input_tokens`, and a computed `cache_hit_ratio` — cache effectiveness is directly observable in structured output, not inferred.

**Cache keep-alive:** Anthropic's ephemeral cache has a 5-minute TTL. Between interview turns, a background task fires a `max_tokens=1` ping every 240 seconds against the same cached static block to reset the TTL. Capped at 12 pings per session. Skipped for `mock` / `ollama` tiers.

---

## Two-tier evaluation

**Haiku evaluation** (`evaluate_answer` tool):
- First classifies the response (`answered / clarification_request / off_topic / refusal`) — off-topic and refusal turns are not scored
- Structured 1–10 score with `signals`, `gaps`, `confidence`, `summary`
- Uses `tool_choice: forced` to guarantee structured JSON output

**Sonnet judge** (internal `judge_evaluation`, not interviewer-callable):
- Adversarially reviews Haiku's score across four axes: signal accuracy, gap fairness, score calibration, confidence validity
- Returns `verdict` (`accept / flag`), `critique`, and optional `adjusted_score`
- Always `claude-sonnet-4-6` regardless of session tier

**Sampling strategy** — judging every answer doubles the evaluation cost. Instead:

| Condition | Always judged |
|---|---|
| First 3 answers | Yes — fairness baseline |
| Confidence == `low` | Yes — signal of evaluator uncertainty |
| Remaining answers | 20% random sample — drift detection |

Expected coverage: ~60% of turns judged without evaluating everything.

**Ordering constraint:** If the LLM calls `evaluate_answer` and `update_hypotheses` in the same turn, the hypothesis update is deferred with an error tool_result, forcing a retry after the evaluation result is visible. This prevents hypotheses from being updated on pre-evaluation reasoning.

---

## Guardrails

Runs on every candidate answer **before the LangGraph graph is invoked**. On a match, returns a safe refusal and skips the graph entirely — the LLM never sees the input.

Three threat categories (regex-based, auditable):

| Category | Example patterns |
|---|---|
| Financial data extraction | "tell me the revenue figures", "what's the EBITDA?" |
| Prompt injection | "ignore previous instructions", "jailbreak", "you are now a DAN" |
| Restricted document access | "show me the policy", "access the confidential doc" |

**NFKC normalization + ASCII folding** runs before pattern matching to defeat homoglyph attacks (Cyrillic `а` → ASCII `a`, etc.).

The API also strips `<candidate_answer>` wrapper tokens from submitted text before re-templating, preventing tag-escape injection into the structured prompt format.

Flagged events are logged in `state["guardrail_events"]` and surfaced in the final debrief.

---

## RAG and data access control

Policy documents (hiring criteria, evaluation standards, competency framework) are retrieved by keyword match at session creation and injected into the static system prompt block.

Access is enforced **structurally**, not by prompt instruction:

1. **Scope gate** — corporate documents are excluded before keyword matching. No prompt can retrieve them.
2. **Sensitivity filtering** — documents carry `public / confidential / restricted` labels. The interviewer persona has `confidential` clearance; restricted documents are dropped at retrieval time, before any LLM call.

---

## Eval scripts

Four headless scripts invoke the graph directly (no HTTP, no FastAPI) for fast, repeatable validation:

| Script | Validates |
|---|---|
| `scripts/score_calibration.py` | Haiku vs Sonnet evaluation delta ≤ 1 across weak / adequate / strong answers |
| `scripts/judge_calibration.py` | Sonnet judge accepts strong answers without over-flagging |
| `scripts/hypothesis_trace.py` | Hypothesis evolution table across a 5-turn session |
| `scripts/adversarial_test.py` | Guardrails block all threat inputs; 0 false negatives |

```bash
uv run python scripts/score_calibration.py
uv run python scripts/judge_calibration.py
uv run python scripts/adversarial_test.py
```

---

## Quick start

```bash
# Install
uv sync

# Backend
source .venv/bin/activate      # Windows: .venv\scripts\activate
cd api && uv run uvicorn main:app --reload

# Frontend (separate terminal)
cd frontend && npm run dev
# → http://localhost:5173
```

Select a model tier in the UI:

| Tier | Models | Cost | Use for |
|---|---|---|---|
| `mock` | None (hardcoded responses) | $0 | Graph wiring, state, SSE |
| `ollama` | Local `llama3.2:3b` | $0 | Streaming, UI rendering |
| `haiku` | Haiku evaluator · Sonnet judge/debrief | Low | Prompt quality, eval accuracy |
| `sonnet` | Sonnet everywhere · extended thinking | Higher | Full reasoning traces |

Set `ANTHROPIC_API_KEY` for `haiku` or `sonnet` tiers.

---

## Key files

| File | What's there |
|---|---|
| [`agent/graph.py`](agent/graph.py) | Graph topology, conditional routing |
| [`agent/nodes.py`](agent/nodes.py) | `interviewer_node` (cache split, streaming, thinking), `tool_node` (judge sampling, deferred update), `debrief_node` |
| [`agent/tools.py`](agent/tools.py) | Tool schemas, `evaluate_answer`, `judge_evaluation`, `update_hypotheses`, `generate_question` |
| [`agent/models.py`](agent/models.py) | Model routing table, `MockAdapter`, `OllamaAdapter`, `call_structured`, `call_text` |
| [`api/routes.py`](api/routes.py) | FastAPI endpoints, SSE streaming, guardrail invocation |
| [`api/keepalive.py`](api/keepalive.py) | Cache keep-alive loop |
| [`app/security/guardrails.py`](app/security/guardrails.py) | Threat detection, NFKC normalization |
| [`app/context/retriever.py`](app/context/retriever.py) | RAG retrieval, scope gate, sensitivity filtering |

---

## Design rationale

**Native SDK instead of LangChain** — `ChatAnthropic` hides `tool_use` block format, extended thinking (`budget_tokens`), prompt caching (`cache_control`), and streaming event granularity. Using the SDK directly keeps all of that visible and controllable.

**Per-task model routing** — evaluation is structured scoring, fast pattern-matching. Haiku handles it accurately at a fraction of the cost. The judge must outrank the evaluator, so it is always Sonnet. The asymmetry is intentional, not an oversight.

**Guardrails pre-graph** — prompt instructions can be bypassed. A screening layer that skips the LLM entirely on flagged input cannot be talked around by the candidate.

**Static/dynamic prompt split** — the CV and JD are stable across turns; hypotheses and history change every turn. Caching only the stable block avoids cache-busting while keeping candidate state current.

---

## What's not here

- Persistent storage (in-memory sessions only)
- User authentication or multi-tenancy
- Vector search (keyword retrieval with scope/sensitivity filtering)
- Fine-tuned models
- Multi-modal input (PDF text extraction only)
