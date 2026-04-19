## Documentation Update Protocol (mandatory — complete before closing any task)

For every file modified, update the corresponding docs:

| File modified | Doc to update |
|--------------|---------------|
| `agent/state.py` | [docs/agent.md](docs/agent.md) State section |
| `agent/graph.py` | [docs/agent.md](docs/agent.md) Graph topology |
| `agent/tools.py` | [docs/agent.md](docs/agent.md) Tools section |
| `agent/models.py` | [docs/model-routing.md](docs/model-routing.md) |
| `agent/prompts.py` | [docs/agent.md](docs/agent.md) System prompt section |
| `api/routes.py` | [docs/api.md](docs/api.md) + [docs/sse-events.md](docs/sse-events.md) if event types change |
| `api/main.py` | [docs/api.md](docs/api.md) App setup section |
| `frontend/src/types.ts` | [docs/frontend.md](docs/frontend.md) Types section |
| `frontend/src/useInterview.ts` | [docs/frontend.md](docs/frontend.md) `useInterview` section |
| `frontend/src/App.css` | [docs/frontend.md](docs/frontend.md) CSS design system section |
| `pyproject.toml` | [docs/index.md](docs/index.md) stack table if deps change |
| Any new file added | [docs/index.md](docs/index.md) |
| Any tool signature changed | [docs/agent.md](docs/agent.md) Tools section + [docs/sse-events.md](docs/sse-events.md) |
| `MODEL_TIER` values changed | [docs/testing-phases.md](docs/testing-phases.md) + [docs/model-routing.md](docs/model-routing.md) |
| Task completed or started | [docs/task.md](docs/task.md) |