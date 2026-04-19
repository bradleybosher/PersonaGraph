/**
 * Custom hook that manages interview session state and SSE streaming.
 * Reads the /api/session SSE stream and maps raw events to UI messages.
 */

import { useCallback, useRef, useState } from 'react'
import type { CandidateProfile, ChatMessage, ModelTier, ParsedDocuments, SSEEvent } from './types'

interface InterviewState {
  sessionId: string | null
  messages: ChatMessage[]
  isStreaming: boolean
  isComplete: boolean
  error: string | null
  questionsRemaining: number
}

export function useInterview(modelTier: ModelTier) {
  const [state, setState] = useState<InterviewState>({
    sessionId: null,
    messages: [],
    isStreaming: false,
    isComplete: false,
    error: null,
    questionsRemaining: 10,
  })

  const sessionIdRef = useRef<string | null>(null)

  // ---------------------------------------------------------------------------
  // SSE reader
  // ---------------------------------------------------------------------------

  const readStream = useCallback(async (response: Response) => {
    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    setState(s => ({ ...s, isStreaming: true, error: null }))

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (!raw) continue

          let event: SSEEvent
          try {
            event = JSON.parse(raw)
          } catch {
            continue
          }

          handleEvent(event)
        }
      }
    } finally {
      setState(s => ({ ...s, isStreaming: false }))
    }
  }, [])

  // ---------------------------------------------------------------------------
  // Event → UI message mapping
  // ---------------------------------------------------------------------------

  function handleEvent(event: SSEEvent) {
    switch (event.type) {
      case 'session_created':
        sessionIdRef.current = event.session_id
        setState(s => ({ ...s, sessionId: event.session_id }))
        break

      case 'thinking_delta':
        // Append to last thinking message if exists, else create new
        setState(s => {
          const msgs = [...s.messages]
          const last = msgs[msgs.length - 1]
          if (last?.kind === 'thinking') {
            msgs[msgs.length - 1] = { kind: 'thinking', content: last.content + event.content }
          } else {
            msgs.push({ kind: 'thinking', content: event.content })
          }
          return { ...s, messages: msgs }
        })
        break

      case 'tool_call':
        setState(s => ({
          ...s,
          messages: [...s.messages, { kind: 'tool_call', name: event.name, input: event.input }],
        }))
        break

      case 'tool_result':
        // Attach result to the last matching tool_call message
        setState(s => {
          const msgs = [...s.messages]
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].kind === 'tool_call' && (msgs[i] as { name: string }).name === event.name) {
              msgs[i] = { ...(msgs[i] as object), result: event.output } as ChatMessage
              break
            }
          }
          return { ...s, messages: msgs }
        })
        break

      case 'question':
        setState(s => ({
          ...s,
          questionsRemaining: event.meta.questions_remaining,
          messages: [
            ...s.messages,
            {
              kind: 'question',
              content: event.content,
              category: event.meta.category,
              depth: event.meta.depth,
              questionsRemaining: event.meta.questions_remaining,
            },
          ],
        }))
        break

      case 'debrief':
        setState(s => ({
          ...s,
          messages: [...s.messages, { kind: 'debrief', content: event.content }],
        }))
        break

      case 'done':
        setState(s => ({ ...s, isStreaming: false, isComplete: true }))
        break

      case 'error':
        setState(s => ({ ...s, error: event.message, isStreaming: false }))
        break
    }
  }

  // ---------------------------------------------------------------------------
  // Public actions
  // ---------------------------------------------------------------------------

  const startSession = useCallback(
    async (candidate: CandidateProfile, docs: ParsedDocuments, tierOverride?: ModelTier) => {
      setState(s => ({ ...s, messages: [], isComplete: false, error: null }))
      const response = await fetch('/api/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidate,
          model_tier: tierOverride ?? modelTier,
          cv_text: docs.cv_text,
          jd_text: docs.jd_text,
        }),
      })
      if (!response.ok) {
        setState(s => ({ ...s, error: `Failed to start session: ${response.statusText}` }))
        return
      }
      await readStream(response)
    },
    [modelTier, readStream],
  )

  const submitAnswer = useCallback(
    async (answer: string) => {
      const sid = sessionIdRef.current
      if (!sid) return

      // Immediately add the answer to the UI
      setState(s => ({
        ...s,
        messages: [...s.messages, { kind: 'answer', content: answer }],
      }))

      const response = await fetch(`/api/session/${sid}/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer }),
      })
      if (!response.ok) {
        setState(s => ({ ...s, error: `Failed to submit answer: ${response.statusText}` }))
        return
      }
      await readStream(response)
    },
    [readStream],
  )

  return { ...state, startSession, submitAnswer }
}
