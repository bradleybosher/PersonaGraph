import { useState } from 'react'
import { ChatView } from './ChatView'
import { IntakeForm } from './IntakeForm'
import { useInterview } from './useInterview'
import type { CandidateProfile, ModelTier, ParsedDocuments } from './types'
import './App.css'

export default function App() {
  const [tier, setTier] = useState<ModelTier>('mock')
  const [started, setStarted] = useState(false)
  const interview = useInterview(tier)

  function handleIntakeComplete(
    candidate: CandidateProfile,
    selectedTier: ModelTier,
    docs: ParsedDocuments,
  ) {
    setTier(selectedTier)
    setStarted(true)
    // Pass selectedTier directly — setTier batches with the render, so the hook
    // closure would still see the old tier without the explicit override.
    interview.startSession(candidate, docs, selectedTier)
  }

  if (!started) {
    return <IntakeForm onComplete={handleIntakeComplete} />
  }

  return (
    <ChatView
      messages={interview.messages}
      isStreaming={interview.isStreaming}
      isComplete={interview.isComplete}
      questionsRemaining={interview.questionsRemaining}
      error={interview.error}
      onSubmit={interview.submitAnswer}
    />
  )
}
