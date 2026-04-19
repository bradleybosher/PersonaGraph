import { useState } from 'react'

interface ThinkingPanelProps {
  content: string
}

export function ThinkingPanel({ content }: ThinkingPanelProps) {
  const [open, setOpen] = useState(true)

  return (
    <div className="thinking-panel">
      <button className="thinking-toggle" onClick={() => setOpen(o => !o)}>
        <span className="thinking-icon">🧠</span>
        <span>{open ? 'Hide' : 'Show'} extended thinking</span>
        <span className="thinking-chevron">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <pre className="thinking-content">{content}</pre>
      )}
    </div>
  )
}
