/**
 * IntakeForm — two-step pre-interview setup.
 *
 * Step 1 (intake): Upload CV PDF + enter JD URL → parse → preview text.
 * Step 2 (profile): Candidate name/background/role + model tier selector.
 *
 * Calls onComplete(candidate, tier, docs) when the user is ready to begin.
 */

import { useState } from 'react'
import type { CandidateProfile, ModelTier, ParsedDocuments } from './types'

interface IntakeFormProps {
  onComplete: (candidate: CandidateProfile, tier: ModelTier, docs: ParsedDocuments) => void
}

const DEFAULT_CANDIDATE: CandidateProfile = {
  name: 'Brad',
  background:
    'Experienced solutions architect with deep knowledge of cloud platforms, enterprise software, and AI/ML systems. Has led technical teams and worked closely with C-suite stakeholders.',
  current_role: 'Senior Solutions Architect',
}

const TIER_HINTS: Record<ModelTier, string> = {
  mock: 'Hardcoded responses — tests graph & streaming. No API calls.',
  ollama: 'Local llama3.2:3b — tests SSE rendering. Requires Ollama running.',
  haiku: 'claude-haiku-4-5 — real intelligence. ~$0.01/session.',
  sonnet: 'claude-sonnet-4-6 + extended thinking — full experience. ~$0.10/session.',
}

export function IntakeForm({ onComplete }: IntakeFormProps) {
  // Step
  const [step, setStep] = useState<'intake' | 'profile'>('intake')

  // Intake step state
  const [cvFile, setCvFile] = useState<File | null>(null)
  const [jdUrl, setJdUrl] = useState('')
  const [isParsing, setIsParsing] = useState(false)
  const [parseError, setParseError] = useState<string | null>(null)
  const [docs, setDocs] = useState<ParsedDocuments | null>(null)

  // Profile step state
  const [candidate, setCandidate] = useState<CandidateProfile>(DEFAULT_CANDIDATE)
  const [tier, setTier] = useState<ModelTier>('mock')

  // ---------------------------------------------------------------------------
  // Step 1 — parse
  // ---------------------------------------------------------------------------

  async function handleParse() {
    if (!cvFile || !jdUrl.trim()) return
    setIsParsing(true)
    setParseError(null)
    setDocs(null)

    const form = new FormData()
    form.append('cv_file', cvFile)
    form.append('jd_url', jdUrl.trim())

    try {
      const res = await fetch('/api/parse', { method: 'POST', body: form })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `HTTP ${res.status}`)
      }
      const parsed: ParsedDocuments = await res.json()
      setDocs(parsed)
    } catch (err) {
      setParseError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsParsing(false)
    }
  }

  // ---------------------------------------------------------------------------
  // Step 2 — begin
  // ---------------------------------------------------------------------------

  function handleBegin() {
    if (!docs) return
    onComplete(candidate, tier, docs)
  }

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  function Preview({ label, text }: { label: string; text: string }) {
    const snippet = text.length > 400 ? text.slice(0, 400) + '…' : text
    return (
      <div className="intake-preview">
        <div className="intake-preview-label">
          {label}
          <span className="intake-preview-chars">{text.length.toLocaleString()} chars</span>
        </div>
        <pre className="intake-preview-text">{snippet}</pre>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="landing">
      <h1>PersonaGraph</h1>
      <p className="subtitle">AI-Powered Interview Practice</p>

      {step === 'intake' && (
        <div className="intake-card">
          <p className="intake-step-label">Step 1 of 2 — Load documents</p>

          <div className="intake-field">
            <label htmlFor="cv-upload">CV / Resume (PDF)</label>
            <input
              id="cv-upload"
              type="file"
              accept=".pdf,application/pdf"
              onChange={e => {
                setCvFile(e.target.files?.[0] ?? null)
                setDocs(null)
                setParseError(null)
              }}
              className="intake-file-input"
            />
            {cvFile && <span className="intake-filename">{cvFile.name}</span>}
          </div>

          <div className="intake-field">
            <label htmlFor="jd-url">Job Description URL</label>
            <input
              id="jd-url"
              type="url"
              placeholder="https://boards.greenhouse.io/..."
              value={jdUrl}
              onChange={e => {
                setJdUrl(e.target.value)
                setDocs(null)
                setParseError(null)
              }}
              className="intake-text-input"
            />
          </div>

          {parseError && (
            <div className="error-banner">{parseError}</div>
          )}

          {docs ? (
            <>
              <Preview label="CV" text={docs.cv_text} />
              <Preview label="Job Description" text={docs.jd_text} />
              <div className="intake-actions">
                <button
                  className="intake-reparse-btn"
                  onClick={() => setDocs(null)}
                >
                  Re-parse
                </button>
                <button
                  className="start-btn"
                  onClick={() => setStep('profile')}
                >
                  Looks good →
                </button>
              </div>
            </>
          ) : (
            <button
              className="start-btn"
              onClick={handleParse}
              disabled={!cvFile || !jdUrl.trim() || isParsing}
            >
              {isParsing ? 'Parsing…' : 'Parse Documents'}
            </button>
          )}
        </div>
      )}

      {step === 'profile' && (
        <div className="intake-card">
          <p className="intake-step-label">Step 2 of 2 — Candidate profile</p>

          <div className="intake-field">
            <label htmlFor="name">Name</label>
            <input
              id="name"
              type="text"
              value={candidate.name}
              onChange={e => setCandidate(c => ({ ...c, name: e.target.value }))}
              className="intake-text-input"
            />
          </div>

          <div className="intake-field">
            <label htmlFor="background">Background</label>
            <textarea
              id="background"
              rows={3}
              value={candidate.background}
              onChange={e => setCandidate(c => ({ ...c, background: e.target.value }))}
              className="intake-textarea"
            />
          </div>

          <div className="intake-field">
            <label htmlFor="current-role">Current Role</label>
            <input
              id="current-role"
              type="text"
              value={candidate.current_role}
              onChange={e => setCandidate(c => ({ ...c, current_role: e.target.value }))}
              className="intake-text-input"
            />
          </div>

          <div className="tier-select">
            <label>Model Tier</label>
            <div className="tier-buttons">
              {(['mock', 'ollama', 'haiku', 'sonnet'] as ModelTier[]).map(t => (
                <button
                  key={t}
                  className={tier === t ? 'active' : ''}
                  onClick={() => setTier(t)}
                >
                  {t}
                </button>
              ))}
            </div>
            <p className="tier-hint">{TIER_HINTS[tier]}</p>
          </div>

          <div className="intake-actions">
            <button
              className="intake-reparse-btn"
              onClick={() => setStep('intake')}
            >
              ← Back
            </button>
            <button
              className="start-btn"
              onClick={handleBegin}
              disabled={!candidate.name.trim()}
            >
              Begin Interview
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
