# Agent — LangGraph Graph, State, Nodes, Tools, Prompts

## State (`agent/state.py`)

```python
class InterviewState(TypedDict):
    messages:             Annotated[list[dict], _add_messages]  # Anthropic format dicts
    candidate:            dict                                   # name, background, current_role
    hypotheses:           dict[str, Hypothesis]                  # per-competency model
    answers:              list[AnswerRecord]                     # full Q&A history with evaluations
    questions_remaining:  int                                    # countdown from 10
    interview_complete:   bool                                   # set True by end_interview tool
    model_tier:           str                                    # "mock"|"ollama"|"haiku"|"sonnet"
    debrief:              Optional[str]                          # final report, populated at end
```

**`_add_messages`** is a plain Python append reducer — no LangChain dependency. Messages are Anthropic-format dicts (`{"role": "...", "content": [...]}`) throughout.

**`Hypothesis`** fields: `signal` (strong/adequate/weak/unknown), `confidence` (0.0–1.0), `notes` (string).

**`JudgeVerdict`** fields: `verdict` (accept/flag), `critique` (string), `adjusted_score` (int or None — only when flagged).

**`AnswerRecord`** fields: `question`, `answer`, `evaluation` (dict from `evaluate_answer` tool), `judge_verdict` (JudgeVerdict or None — None for mock/ollama tiers).

Five competencies are pre-populated in `initial_state()`:
- `leadership`
- `technical_depth`
- `agentic_systems`
- `customer_empathy`
- `strategic_thinking`

## Graph topology (`agent/graph.py`)

```
START
  └─► interviewer_node   (Sonnet + extended thinking, all 4 tools)
            │
            ├─[tool_use blocks present]──► tool_node
            │                                  │
            │   ◄───────────────────────────────┤  [no generate_question in this pass]
            │                                  │
            │                 [generate_question was called]──► END  (pause; wait for answer)
            │
            ├─[plain text, questions remain]──► END  (Ollama tier; pause; wait for answer)
            │
            └─[no tool calls, complete, or out of questions]──► debrief_node ──► END
```

### Routing functions

**`_route_after_interviewer(state)`**
- If last assistant message has `tool_use` blocks → `"tool_node"`
- If `interview_complete` or `questions_remaining <= 0` → `"debrief_node"`
- If last assistant message has plain text (Ollama tier) → `END` (pause; wait for answer)
- Safety fallback (no tool calls, no text) → `"debrief_node"`

**`_route_after_tools(state)`**
- `interview_complete` or `questions_remaining <= 0` → `"debrief_node"`
- `generate_question` tool was in the last assistant message → `END` (graph pauses; caller awaits next answer submission)
- Otherwise → `"interviewer_node"` (more tool calls needed in this turn, e.g., evaluate then generate)

The pause-on-question routing is what makes each `ainvoke()` call correspond to exactly one Q&A turn. The SSE route calls `ainvoke()` once per HTTP request.

## Nodes (`agent/nodes.py`)

### `interviewer_node(state, config)`

Runs the interviewer LLM. Config carries `event_queue` (asyncio.Queue) for SSE emission.

**Mock/Ollama path:** Calls `adapter.complete_messages()`, emits `thinking` and `tool_call` events from the returned message dict.

**Real Anthropic path (haiku/sonnet):** Calls `client.messages.stream()` with:
- `model`: `claude-sonnet-4-6`
- `thinking`: `{"type": "enabled", "budget_tokens": 5000}` (sonnet tier only)
- `tools`: all 4 `TOOL_SCHEMAS`
- `system`: `build_system_prompt(state)`
- `messages`: `state["messages"]`

Prompt caching: if the first message is a plain-string user message, it's rewritten as a content block with `cache_control: {"type": "ephemeral"}`. By question 5 this saves ~60% on Sonnet input tokens.

Streaming events emitted in real-time:
- `thinking_delta` — per-chunk during thinking block
- `thinking` — full thinking block at `content_block_stop`
- `tool_call` — at each `tool_use` content_block_stop

Returns `{"messages": [assistant_message_dict]}`.

### `tool_node(state, config)`

Dispatches all `tool_use` blocks in the last assistant message via `TOOL_REGISTRY`. Applies state side-effects:

| Tool | Side-effect |
|------|------------|
| `evaluate_answer` | Runs `judge_evaluation` (Sonnet); appends `AnswerRecord` (with `judge_verdict`) to `state["answers"]`; emits `judge_verdict` SSE event; logs `evaluation_result` |
| `update_hypotheses` | Replaces `state["hypotheses"]`; logs `hypotheses_updated` with per-competency signal + confidence |
| `generate_question` | Decrements `state["questions_remaining"]`; emits `question` SSE event; logs `question_generated` with category + depth |
| `end_interview` | Sets `state["interview_complete"] = True` |

Emits `tool_result` SSE event for every tool call. For `evaluate_answer`, the tool result content is `{"evaluation": {...}, "judge_verdict": {...}}` — both are visible to the interviewer when updating hypotheses.

**Structured log events emitted:**
- `evaluation_result` — `session_id`, `turn`, `score`, `signals`, `gaps`, `confidence_eval`, `judge_verdict`, `judge_adjusted_score`
- `hypotheses_updated` — `session_id`, `turn`, `hypotheses` (signal + confidence per competency)
- `question_generated` — `session_id`, `turn`, `category`, `depth`, `questions_remaining`

Returns `{"messages": [tool_results_user_message], **state_updates}`.

Tool results are formatted as Anthropic multi-turn tool result messages:
```python
{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]}
```

### `debrief_node(state, config)`

Generates the final hiring assessment.

**Mock/Ollama:** Returns hardcoded debrief text. Emits `debrief_start`, `debrief`, `done`.

**Real Anthropic:** Builds a prompt from `state["answers"]` and `state["hypotheses"]`, calls `call_text()` with Sonnet. Emits the same three events.

## Tools (`agent/tools.py`)

All 4 tools are given to the interviewer simultaneously. No forced call order.

### `evaluate_answer(question, answer, model_tier) → dict`

Calls Haiku via `call_structured()` with `tool_choice: {type: "tool", name: "structured_output"}` to force valid JSON. Schema:
```python
{"score": int(1-10), "signals": [str], "gaps": [str], "confidence": "low|medium|high", "summary": str}
```

### `update_hypotheses(hypotheses, model_tier) → dict`

Pass-through — the interviewer LLM provides the updated dict directly in its tool call input. No sub-model call. `tool_node` writes this to state.

### `generate_question(category, depth, rationale, model_tier) → str`

Calls Sonnet via `call_text()`. Prompt specifies the competency, depth guidance, and rationale. Returns a single question string. Depth values:
- `surface` — broad opener
- `probe` — targeted follow-up
- `deep_dive` — stress test / challenging scenario

### `end_interview(rationale, model_tier) → dict`

Returns `{"acknowledged": True, "rationale": rationale}`. `tool_node` sets `interview_complete = True`.

### `judge_evaluation(question, answer, evaluation, model_tier) → dict | None`

LLM-as-a-judge: adversarially validates Haiku's evaluation using Sonnet. Called automatically in `tool_node` after every `evaluate_answer` — not an interviewer-callable tool.

Returns `None` for mock/ollama tiers. For real API tiers, always uses Sonnet (ignores session tier — judge must outrank evaluator). Returns a `JudgeVerdict` dict with four-point critique:
1. Signal accuracy — are listed signals actually present?
2. Gap fairness — are gaps valid for this seniority/role?
3. Score calibration — is 7 = clear hire signal correctly applied?
4. Confidence validity — does stated confidence match answer clarity?

## System prompt (`agent/prompts.py`)

`build_system_prompt(state)` assembles a dynamic prompt containing:

1. **Candidate profile** — name, background, current role
2. **Goal** — form a complete picture in `N` remaining questions
3. **Competency areas** — 5 named areas
4. **Current hypotheses** — signal, confidence, notes for each competency
5. **Interview history** — compact Q&A summary with scores
6. **Tool usage rules** — call order guidance, when to use `end_interview`
7. **Turn instruction** — opening message (no prior answers) vs. follow-up (answer provided)

The turn instruction is the key adaptive element: on follow-up turns it includes the candidate's last answer and instructs the model to evaluate → update → decide → (generate or end). The instruction also tells the interviewer that `evaluate_answer` tool results contain both `evaluation` and `judge_verdict`, and to weight `adjusted_score` over raw score when the judge flags an evaluation.

`build_judge_prompt(question, answer, evaluation)` generates the adversarial validation prompt used by `judge_evaluation`. It is not part of the system prompt — it's called as a one-shot message to Sonnet in the tool layer.
