export type ModelTier = 'mock' | 'ollama' | 'haiku' | 'sonnet'

export interface CandidateProfile {
  name: string
  background: string
  current_role: string
}

export interface ParsedDocuments {
  cv_text: string
  jd_text: string
}

// SSE event shapes from the backend
export type SSEEvent =
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

// UI message shapes
export interface ThinkingMessage {
  kind: 'thinking'
  content: string
}

export interface ToolCallMessage {
  kind: 'tool_call'
  name: string
  input: Record<string, unknown>
  result?: unknown
}

export interface QuestionMessage {
  kind: 'question'
  content: string
  category: string
  depth: string
  questionsRemaining: number
}

export interface AnswerMessage {
  kind: 'answer'
  content: string
}

export interface DebriefMessage {
  kind: 'debrief'
  content: string
}

export type ChatMessage =
  | ThinkingMessage
  | ToolCallMessage
  | QuestionMessage
  | AnswerMessage
  | DebriefMessage
