# SSE Event Contract

All events are sent as `data: <json>\n\n` over `text/event-stream`. The frontend parses them in `useInterview.ts:handleEvent()`.

## Event types

### `session_created`
Emitted once at the start of `POST /api/session`. Always the first event.

```json
{"type": "session_created", "session_id": "uuid-string", "model_tier": "mock"}
```

Frontend effect: stores `session_id` in `sessionIdRef` for subsequent answer submissions.

---

### `thinking_delta`
Streaming chunk of extended thinking text. Emitted during `content_block_delta` for thinking blocks (Sonnet tier only).

```json
{"type": "thinking_delta", "content": "partial thinking text..."}
```

Frontend effect: appended to the last `ThinkingMessage` if it exists; otherwise a new one is created.

---

### `thinking`
Complete thinking block, emitted at `content_block_stop`. Also emitted by MockAdapter as a single event.

```json
{"type": "thinking", "content": "full thinking text"}
```

Frontend effect: same append/create logic as `thinking_delta`. In practice both events may arrive for the same block (delta during stream, full at stop).

---

### `tool_call`
Emitted when the interviewer calls a tool. Arrives before the result.

```json
{"type": "tool_call", "name": "evaluate_answer", "input": {"question": "...", "answer": "..."}}
```

Frontend effect: pushes a `ToolCallMessage` with `result: undefined` (shows "…" status badge).

---

### `tool_result`
Emitted after a tool has been executed.

```json
{"type": "tool_result", "name": "evaluate_answer", "output": {"score": 7, "signals": [...], ...}}
```

Frontend effect: attaches `result` to the last `ToolCallMessage` with matching `name` (shows "✓" status badge).

---

### `judge_verdict`
Emitted after `judge_evaluation` (Sonnet) validates Haiku's `evaluate_answer` output. Arrives between the `tool_call` and `tool_result` events for `evaluate_answer`. Only emitted for `haiku` and `sonnet` tiers.

```json
{
  "type": "judge_verdict",
  "verdict": "accept",
  "critique": "Score and signals are well-calibrated for this answer.",
  "adjusted_score": null,
  "tool_use_id": "toolu_01..."
}
```

`verdict` is `"accept"` (evaluation is fair) or `"flag"` (evaluation has a material flaw). `adjusted_score` is an integer only when `verdict="flag"`.

Frontend effect: attaches verdict badge to the corresponding `evaluate_answer` tool call. `tool_use_id` links back to the `evaluate_answer` tool_use block.

---

### `question`
Emitted when `generate_question` tool is called and a question has been produced.

```json
{
  "type": "question",
  "content": "Tell me about a time you...",
  "meta": {
    "category": "leadership",
    "depth": "surface",
    "questions_remaining": 9
  }
}
```

Frontend effect: pushes a `QuestionMessage`, updates `questionsRemaining` counter in header.

---

### `debrief_start`
Signals that the debrief phase has begun. No content — used to show a loading state if needed.

```json
{"type": "debrief_start"}
```

Frontend effect: currently unused in UI; reserved for future loading indicator.

---

### `debrief`
The final hiring assessment text.

```json
{"type": "debrief", "content": "**Overall Assessment:**\n..."}
```

Frontend effect: pushes a `DebriefMessage`, rendered as a full-width amber card.

---

### `done`
Final event in every stream. Signals the interview or turn is complete.

```json
{"type": "done"}
```

Frontend effect: sets `isComplete: true` and `isStreaming: false`. Input area is hidden.

---

### `error`
Emitted when the graph throws an exception.

```json
{"type": "error", "message": "Exception text"}
```

Frontend effect: sets `error` string, displayed in a red error banner. `isStreaming` is set to false.

## Event ordering

Typical opening turn:
```
session_created
thinking          (or thinking_delta × N, then thinking)
tool_call         (generate_question)
question
tool_result       (generate_question)
```

Typical follow-up turn:
```
thinking
tool_call         (evaluate_answer)
tool_call         (generate_question)
judge_verdict     (evaluate_answer — haiku/sonnet tiers only)
tool_result       (evaluate_answer)
question
tool_result       (generate_question)
```

Final turn:
```
thinking
tool_call         (evaluate_answer)
tool_call         (end_interview)
judge_verdict     (evaluate_answer — haiku/sonnet tiers only)
tool_result       (evaluate_answer)
tool_result       (end_interview)
debrief_start
debrief
done
```

## Notes

- `tool_call` arrives before `tool_result` for the same tool — the frontend renders the badge immediately and adds ✓ when result arrives.
- The `tool_result` for `generate_question` arrives **after** the `question` event. The frontend renders the question first (better UX) and the result fills in the badge silently.
- `thinking_delta` and `thinking` may both arrive for the same block during a real Sonnet session. The frontend handles this by accumulating all content into a single `ThinkingMessage`.
