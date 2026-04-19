import { useEffect, useRef, useState } from 'react'
import { ThinkingPanel } from './ThinkingPanel'
import type { ChatMessage } from './types'

// Ambient declarations for Web Speech API (not in default TS lib)
interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList
}
interface SpeechRecognitionInstance {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: ((e: SpeechRecognitionEvent) => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
  start(): void
  stop(): void
}
declare var SpeechRecognition: (new () => SpeechRecognitionInstance) | undefined
declare var webkitSpeechRecognition: (new () => SpeechRecognitionInstance) | undefined

interface ChatViewProps {
  messages: ChatMessage[]
  isStreaming: boolean
  isComplete: boolean
  questionsRemaining: number
  error: string | null
  onSubmit: (answer: string) => void
}

const DEPTH_LABEL: Record<string, string> = {
  surface:   'Opening',
  probe:     'Probe',
  deep_dive: 'Deep dive',
}

export function ChatView({
  messages,
  isStreaming,
  isComplete,
  questionsRemaining,
  error,
  onSubmit,
}: ChatViewProps) {
  const [draft, setDraft] = useState('')
  const [isListening, setIsListening] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const SpeechRecognitionImpl =
    typeof SpeechRecognition !== 'undefined' ? SpeechRecognition :
    typeof webkitSpeechRecognition !== 'undefined' ? webkitSpeechRecognition :
    null

  function toggleMic() {
    if (isListening) {
      setIsListening(false)
      return
    }
    if (!SpeechRecognitionImpl) return
    const recognition = new SpeechRecognitionImpl()
    recognition.continuous = false
    recognition.interimResults = false
    recognition.lang = 'en-US'
    recognition.onresult = (e) => {
      const transcript = e.results[0][0].transcript
      setDraft(prev => prev ? `${prev} ${transcript}` : transcript)
    }
    recognition.onend = () => setIsListening(false)
    recognition.onerror = () => setIsListening(false)
    setIsListening(true)
    recognition.start()
  }

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus input when streaming stops and interview isn't complete
  useEffect(() => {
    if (!isStreaming && !isComplete) {
      inputRef.current?.focus()
    }
  }, [isStreaming, isComplete])

  function handleSubmit() {
    const trimmed = draft.trim()
    if (!trimmed || isStreaming || isComplete) return
    setDraft('')
    onSubmit(trimmed)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="chat-view">
      {/* Header */}
      <header className="chat-header">
        <span className="chat-title">PersonaGraph</span>
        <span className="questions-badge">
          {isComplete ? 'Complete' : `${questionsRemaining} questions remaining`}
        </span>
      </header>

      {/* Message list */}
      <div className="message-list">
        {messages.map((msg, i) => {
          switch (msg.kind) {
            case 'thinking':
              return <ThinkingPanel key={i} content={msg.content} />

            case 'tool_call':
              return (
                <div key={i} className="tool-badge">
                  <span className="tool-name">⚙ {msg.name}</span>
                  <span className="tool-status">
                    {'result' in msg ? '✓' : '…'}
                  </span>
                </div>
              )

            case 'question':
              return (
                <div key={i} className="message interviewer">
                  <div className="message-meta">
                    <span className="meta-role">Interviewer</span>
                    <span className="meta-category">{msg.category}</span>
                    <span className="meta-depth">{DEPTH_LABEL[msg.depth] ?? msg.depth}</span>
                  </div>
                  <p className="message-body">{msg.content}</p>
                </div>
              )

            case 'answer':
              return (
                <div key={i} className="message candidate">
                  <div className="message-meta">
                    <span className="meta-role">You</span>
                  </div>
                  <p className="message-body">{msg.content}</p>
                </div>
              )

            case 'debrief':
              return (
                <div key={i} className="debrief-card">
                  <h3>Final Assessment</h3>
                  <pre className="debrief-body">{msg.content}</pre>
                </div>
              )

            default:
              return null
          }
        })}

        {isStreaming && (
          <div className="streaming-indicator">
            <span className="dot" /><span className="dot" /><span className="dot" />
          </div>
        )}

        {error && <div className="error-banner">{error}</div>}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      {!isComplete && (
        <div className="input-row">
          <textarea
            ref={inputRef}
            className="answer-input"
            placeholder="Type your answer… (Enter to send, Shift+Enter for new line)"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
            rows={3}
          />
          {SpeechRecognitionImpl && (
            <button
              className={`mic-btn${isListening ? ' listening' : ''}`}
              onClick={toggleMic}
              disabled={isStreaming}
              title={isListening ? 'Stop recording' : 'Speak your answer'}
            >
              {isListening ? '⏹' : '🎤'}
            </button>
          )}
          <button
            className="send-btn"
            onClick={handleSubmit}
            disabled={isStreaming || !draft.trim()}
          >
            Send
          </button>
        </div>
      )}
    </div>
  )
}
