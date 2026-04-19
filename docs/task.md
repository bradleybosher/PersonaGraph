# Task Log

## Current status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | `mock` — graph, SSE, UI | ✅ Complete |
| 2 | `ollama` — streaming, Q&A loop, debrief | ✅ Complete |
| 2.5 | CV/JD ingestion — parse PDF + URL into prompt cache | ✅ Complete |
| 3 | `haiku` quality tuning | ✅ Complete |
| 4 | `sonnet` polish | ⬜ Blocked on Phase 3 |
| — | LLM-as-judge (adversarial evaluation validation) | ✅ Complete |
| — | Cache telemetry + 5-min keep-alive + enterprise review doc | ✅ Complete |
| — | Cost optimisation: conditional judge + debrief max_tokens fix | ✅ Complete |

See [testing-phases.md](testing-phases.md) for commands and pass criteria per phase.

---

## Outstanding tasks

### Quality verification scripts (ready to run)
- `scripts/score_calibration.py` — Haiku vs Sonnet calibration check (Option 1)
- `scripts/hypothesis_trace.py` — Hypothesis coherence check (Option 2)
- `scripts/adversarial_test.py` — Adversarial answer test (Option 3)

### Phase 4 — Sonnet polish
- Run `MODEL_TIER=sonnet` and review:
  - Extended thinking content in the panel
  - Strategic adaptation (category shifts, early termination)
  - Deep-dive question quality
  - Debrief specificity and evidence quality
- Verify prompt caching is active (check Anthropic dashboard for cache read tokens)

### Prompt tuning (likely needed in Phase 3)
- System prompt turn instruction may need adjustment if real LLM doesn't follow tool call order
- Evaluation rubric may need score calibration after seeing real outputs
- Hypothesis update format may need constraint to prevent drift

### UI improvements (nice-to-have, not blocking)
- Debrief card could render markdown instead of plain `<pre>` text
- Tool call badges could be collapsible to reduce visual noise in long sessions
- Error recovery: reconnect to existing session if SSE stream drops (use `GET /api/session/{id}`)
- Consider adding a "Start over" button on the complete screen

### Production hardening (out of scope for interview demo)
- Replace in-memory `_sessions` store with Redis or SQLite for persistence
- Add session expiry (TTL on inactive sessions)
- Auth (API key gate on backend endpoints)
- Rate limiting
- Deployment config (Dockerfile, env injection)
