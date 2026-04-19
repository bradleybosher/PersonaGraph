# Frontend — React + Vite Chat UI

## File map

```
frontend/src/
├── main.tsx          — React entry point, mounts App into #root
├── index.css         — Minimal reset (body height, font, dark bg)
├── App.tsx           — Landing page + tier selection; renders ChatView after start
├── App.css           — Full design system (see CSS section below)
├── types.ts          — TypeScript types for SSE events and UI messages
├── useInterview.ts   — Custom hook: SSE client, session state, submit actions
├── ChatView.tsx      — Chat layout: header, message list, input row
└── ThinkingPanel.tsx — Collapsible extended thinking display
```

## Component responsibilities

### `App.tsx`

Landing page state machine. Renders:
- Tier selector buttons (mock / ollama / haiku / sonnet)
- Tier hint text explaining cost and capability
- "Begin Interview" button

On start: calls `interview.startSession(candidate)` and switches to `<ChatView>`.

`DEFAULT_CANDIDATE` is hardcoded with Brad's profile. This is intentional — the tool is for a specific interview, not generic.

### `ChatView.tsx`

Stateless display component. Receives all state as props from `useInterview`. Renders:

| Message kind | Rendered as |
|---|---|
| `thinking` | `<ThinkingPanel>` (collapsible) |
| `tool_call` | Badge with tool name and ✓/… status |
| `question` | Interviewer bubble with category + depth meta tags |
| `answer` | Candidate bubble |
| `debrief` | Full-width assessment card |

Auto-scrolls to bottom on new messages (`useEffect` on `messages`). Focuses the textarea when streaming stops.

Input: textarea with Enter-to-send (Shift+Enter = newline). Disabled during streaming.

### `ThinkingPanel.tsx`

Toggle button showing "🧠 Show/Hide extended thinking." Renders thinking content in a `<pre>` block when open. Starts collapsed.

### `useInterview.ts`

Custom hook managing all session state and server communication.

**State shape:**
```ts
interface InterviewState {
  sessionId: string | null
  messages: ChatMessage[]
  isStreaming: boolean
  isComplete: boolean
  error: string | null
  questionsRemaining: number
}
```

**`readStream(response)`** reads `response.body` as a `ReadableStream`, buffers across chunks, splits on `\n`, parses `data: {...}` lines, calls `handleEvent()`.

**`handleEvent(event)`** maps SSE events to state updates:
- `session_created` → stores `sessionId` in a ref (survives re-renders without triggering effects)
- `thinking_delta` → appends to last thinking message or creates new one
- `tool_call` → pushes `ToolCallMessage`
- `tool_result` → attaches `.result` to the last matching `tool_call` message by name
- `question` → pushes `QuestionMessage`, updates `questionsRemaining`
- `debrief` → pushes `DebriefMessage`
- `done` → sets `isComplete: true`
- `error` → sets `error` string

**`startSession(candidate)`** → `POST /api/session`, calls `readStream`.

**`submitAnswer(answer)`** → immediately appends `AnswerMessage` to UI (optimistic), then `POST /api/session/{id}/answer`, calls `readStream`.

`sessionIdRef` is a `useRef` (not state) because `submitAnswer` needs the current session ID without being recreated on every render.

## Types (`types.ts`)

**SSE events** — discriminated union on `type`:
```ts
type SSEEvent =
  | { type: 'session_created'; session_id: string; model_tier: ModelTier }
  | { type: 'thinking_delta'; content: string }
  | { type: 'thinking'; content: string }
  | { type: 'tool_call'; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; name: string; output: unknown }
  | { type: 'question'; content: string; meta: { category: string; depth: string; questions_remaining: number } }
  | { type: 'debrief_start' }
  | { type: 'debrief'; content: string }
  | { type: 'done' }
  | { type: 'error'; message: string }
```

**UI messages** — discriminated union on `kind` (separate from SSE events — the hook maps between them):
```ts
type ChatMessage =
  | ThinkingMessage    // kind: 'thinking'
  | ToolCallMessage    // kind: 'tool_call', includes optional result
  | QuestionMessage    // kind: 'question', includes category, depth, questionsRemaining
  | AnswerMessage      // kind: 'answer'
  | DebriefMessage     // kind: 'debrief'
```

## CSS design system (`App.css`)

Dark theme. Key CSS custom properties:

| Variable | Value | Used for |
|----------|-------|---------|
| `--bg` | `#0d0d0f` | Page background |
| `--surface` | `#16161a` | Header, input row, thinking toggle, tier buttons |
| `--border` | `#2a2a2e` | All borders |
| `--text` | `#e4e4e7` | Body text |
| `--text-muted` | `#71717a` | Meta labels, muted content |
| `--accent` | `#d97706` | Amber — active states, send button, debrief border |
| `--interviewer` | `#1e2a3a` | Interviewer message background |
| `--candidate` | `#1a2a1e` | Candidate message background |

Key layout classes:
- `.chat-view` — flex column, full viewport height
- `.message-list` — scrollable flex column, `gap: 16px`
- `.thinking-panel` — collapsible container with toggle button
- `.tool-badge` — inline pill with tool name and status icon
- `.debrief-card` — amber-bordered full-width assessment block
- `.streaming-indicator` — three animated dots (CSS `@keyframes blink`)

## Vite proxy

`vite.config.ts` proxies `/api` → `http://localhost:8000`. No CORS configuration needed in development — all requests go through the same origin from the browser's perspective.

## TypeScript

`tsconfig.app.json` targets ES2020 with strict mode. Zero type errors as of last check.

```bash
cd frontend && npx tsc --noEmit   # should produce no output
```
