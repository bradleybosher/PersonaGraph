# Architecture — PersonaGraph

## Purpose

This project is a working interview practice tool built to explore enterprise-grade agentic systems patterns. Every architectural decision was made to be **explainable and defensible** in production agentic systems.

## Core design choices

LangChain's `ChatAnthropic` wrapper was rejected because it abstracts away:
- Claude's native `tool_use` block format
- Extended thinking (`thinking` content blocks, `budget_tokens`)
- Prompt caching (`cache_control: ephemeral` on message blocks)
- Streaming event granularity (`content_block_start`, `input_json_delta`, `thinking_delta`)

Showing mastery of the native SDK is a stronger signal than knowing a wrapper.

### True agent

The implementation gives the interviewer **all 4 tools simultaneously** with no forced call order. The LLM decides:
- Whether to evaluate at all (might skip on a clarifying follow-up)
- Whether to update hypotheses or just generate the next question
- Whether to end early if it has enough signal
- How many tools to call in a single turn

LangGraph conditional edges are driven entirely by what the LLM returned — not by a predetermined sequence.

### Per-task model routing (not per-role)

The implementation routes by **task complexity**:

| Task | Model | Why |
|------|-------|-----|
| Interviewer orchestration | Sonnet + extended thinking | Strategy is non-deterministic |
| `generate_question` | Sonnet | User-facing output; quality matters |
| `evaluate_answer` | Haiku | Structured scoring; pattern match |
| `judge_evaluation` | Sonnet (always) | Judge must outrank evaluator regardless of session tier |
| `update_hypotheses` | No sub-model | LLM provides update directly via tool call |
| `end_interview` | No sub-model | State signal only |
| Debrief | Sonnet | Final report quality matters |

### LLM-as-a-judge (adversarial evaluation validation)

After Haiku scores each answer, a Sonnet judge adversarially reviews the evaluation before it influences the interviewer's hypothesis updates. Four checks:

1. **Signal accuracy** — are listed strengths actually in the answer, or hallucinated?
2. **Gap fairness** — are identified weaknesses valid for this seniority/role?
3. **Score calibration** — is 7 correctly applied as a clear hire signal for this role?
4. **Confidence validity** — does the stated confidence level match how clearly the answer demonstrated the competency?

The judge can `accept` (evaluation is fair) or `flag` (material flaw, provides adjusted score). The interviewer sees both the raw Haiku evaluation and the judge verdict in the tool result, and is instructed to weight `adjusted_score` over the raw score when flagged.

**When the judge fires:** The judge runs on the first 3 answers unconditionally (establishing a fairness baseline) and on any subsequent answer where Haiku returns `confidence == "low"`. High-confidence evaluations after turn 3 are accepted without a second review — Haiku's calibration is verified by the earlier turns. This reduces judge calls from 10 → ~4–5 per session (~21% cost reduction) while preserving the audit trail on uncertain and early decisions.

**Why this matters architecturally:** Single-model evaluations can be biased or miscalibrated. This creates a defense-in-depth layer with an explicit adversarial validation step — not trusting the first LLM's output, but checking it with a more capable model before it shapes the hiring assessment. Every evaluated answer has a `judge_verdict` field in state (either a verdict dict or `null` for auto-approved turns), visible in the debrief.

→ Full routing table, adapter details, and prompt caching implementation: [model-routing.md](model-routing.md)

### Phased testing with cost control

| Phase | Tier | Purpose | Cost |
|-------|------|---------|------|
| 1 | `mock` | Graph, state, SSE wiring — zero API calls | $0 |
| 2 | `ollama` | SSE pipe + UI rendering with a live stream | $0 |
| 3 | `haiku` | Prompt quality and evaluation accuracy | ~$0.015/session |
| 4 | `sonnet` | Extended thinking, debrief quality, full experience | ~$0.076/session |

Each phase has a clear validation criterion before moving on. This is standard development discipline for systems that interact with paid APIs.

→ Commands, pass criteria, and current status per phase: [testing-phases.md](testing-phases.md)

### Extended thinking visible in the UI

The `thinking` content blocks stream in real-time to a collapsible panel in the frontend. This makes the reasoning loop tangible to anyone watching the demo — not an abstract claim about "the model reasons."

## Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Agent graph | LangGraph 0.2+ | Conditional edges, state management, composable nodes |
| LLM calls | `anthropic` SDK (native) | Full access to thinking, caching, streaming events |
| Backend | FastAPI + SSE | Async, lightweight, SSE via `StreamingResponse` |
| Frontend | React + Vite | Fast setup, custom SSE client with `fetch` + `ReadableStream` |
| Config | `MODEL_TIER` env var | Single switch to change entire model routing |

## Key design constraints

- **No auth, no persistence beyond in-memory session store** — this is a demo, not a product
- **Single chat route** — the frontend scope is deliberately narrow
- **No LangChain** — ever, for any reason, in this project
- **Every architectural decision should survive "why did you choose X?"**
