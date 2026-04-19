# Model Routing — Adapters, Task Selection, Prompt Caching

## Routing table

Routing is by **task complexity**, not by role. This is a deliberate architectural choice — see [architecture.md](architecture.md) for the rationale.

| Task key | Model (haiku/sonnet tiers) | Why |
|----------|--------------------------|-----|
| `interviewer` | `claude-sonnet-4-6` | Non-deterministic strategy; extended thinking |
| `question_gen` | `claude-sonnet-4-6` | User-facing output; quality matters |
| `evaluation` | `claude-haiku-4-5-20251001` | Structured JSON scoring; Haiku is 95% as good at 10% the cost |
| `judge` | `claude-sonnet-4-6` | Always Sonnet — judge must outrank evaluator regardless of session tier |
| `debrief` | `claude-sonnet-4-6` | Final report quality matters |
| `update_hypotheses` | *(no sub-model)* | LLM provides update in tool call input directly |
| `end_interview` | *(no sub-model)* | State signal only |

```python
def get_anthropic_model(task: str) -> str:
    tier_key = _TASK_MODEL_TIER.get(task, "haiku")
    return _ANTHROPIC_MODELS[tier_key]
```

## Adapters

### MockAdapter (tier: `mock`)

Zero API calls. Returns hardcoded valid responses from `RESPONSES` dict.

`complete_messages()` behaviour:
- **Opening turn** (no prior user answer in messages): returns assistant message with `generate_question` tool call only
- **Follow-up turn** (user answer string present): returns assistant message with `evaluate_answer` + `generate_question` tool calls, simulating realistic multi-tool turn

Used in Phase 1 to test graph, state, and SSE wiring without spending API credits.

### OllamaAdapter (tier: `ollama`)

Calls local `llama3.2:3b` at `OLLAMA_BASE_URL` (default: `http://localhost:11434/api/chat`).

**Scope**: interviewer node only. Does **not** handle tool_use calls — small models cannot reliably produce valid tool_use JSON. During the `ollama` tier, tools remain mocked.

Used in Phase 2 to test SSE streaming latency, thinking panel collapse/expand, and UI rendering with a live stream that has variable timing. If Ollama produces garbled output, that's expected — the goal is to test the pipe, not the intelligence.

`_flatten_content()` collapses Anthropic content blocks to plain strings for Ollama's simpler API format.

## Caller helpers

### `call_structured(prompt, output_schema, model)`

Forces structured JSON output via `tool_choice: {"type": "tool", "name": "structured_output"}`. Used by `evaluate_answer` (Haiku) to guarantee a parseable evaluation dict.

This is the correct pattern for extracting structured data from Claude — not asking for JSON in the prompt, but forcing a tool call.

### `call_text(prompt, model, max_tokens=512)`

Plain `messages.create()` call, returns first text block. Used by `generate_question` (Sonnet, default 512 tokens) and `debrief_node` (768 tokens — enough headroom for the 300–400 word hiring assessment without truncation).

## Prompt caching

Applied in `interviewer_node` on the real Anthropic path. The system prompt is split into two blocks so only the unchanging content is cached:

```python
"system": [
    {
        "type": "text",
        "text": build_static_prompt(cv_text, jd_text),   # JD + CV — never changes
        "cache_control": {"type": "ephemeral"},
    },
    {
        "type": "text",
        "text": build_dynamic_prompt(state),             # hypotheses + history — fresh each turn
    },
],
```

The static block (JD + CV, ~2–4k tokens) is the cache read target; the dynamic block carries whatever the interviewer needs current. Getting the boundary right is what makes caching actually pay off — caching the dynamic content would cause every turn to register as a cache miss.

### Verifying the cache is working

Every API call emits a `anthropic_api_call` JSON log line with `cache_read_input_tokens`, `cache_creation_input_tokens`, and a computed `cache_hit_ratio`. Expected pattern on a real-API session:

- Turn 1: `cache_creation_input_tokens > 0`, `cache_read_input_tokens == 0`.
- Turn 2+: `cache_read_input_tokens > 0`, `cache_creation_input_tokens` small.
- `cache_hit_ratio > 0.6` by turn 3.

### 5-minute TTL and keep-alive

Ephemeral cache TTL is 5 minutes. If a candidate takes longer than that to compose an answer, the static block is evicted and the next turn pays full input cost. Mitigated by the keep-alive loop in [api/keepalive.py](../api/keepalive.py) — see [api.md](api.md#cache-keep-alive-apikeepalivepy).

## Logging (`api/logging_config.py`)

Single JSON logger (`interview_coach`), stdout. The `log_api_usage()` helper in `agent/models.py` is called from every Anthropic call site (`interviewer_node`, `call_structured`, `call_text`, `cache_keepalive`) so per-call token + cache counts are always comparable across nodes.

## `MODEL_TIER` env var

Single switch that routes the entire application:

| Value | Adapter | Anthropic calls |
|-------|---------|----------------|
| `mock` | MockAdapter for all nodes | None |
| `ollama` | OllamaAdapter for interviewer; MockAdapter for tools | None |
| `haiku` | None | Haiku for evaluation; Sonnet for judge, question_gen, debrief, interviewer |
| `sonnet` | None | Same routing as haiku, plus extended thinking on interviewer |

The `haiku` tier still uses Sonnet for question generation and the interviewer — "haiku tier" means Haiku is used where it's appropriate (evaluation), not that everything uses Haiku.
