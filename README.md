# ResumePilot AI

Production-grade AI platform for resume analysis. This repository currently contains
only the project scaffold — no business logic.

## Stack

- Python 3.12+, managed with [uv](https://docs.astral.sh/uv/)
- FastAPI (async) served by uvicorn
- Pydantic Settings for configuration
- structlog for structured (JSON) logging
- pytest + httpx for testing
- Ruff for linting/formatting
- Docker / Docker Compose for containerized runs

## Project layout

```
src/app/
  app.py               # FastAPI application factory
  main.py               # process entrypoint (uvicorn runner)
  core/
    config.py           # Pydantic Settings (env-driven)
    logging.py           # structlog configuration
  api/
    router.py            # top-level API router
    v1/
      router.py           # /v1 router
      endpoints/
        health.py           # GET /v1/health
tests/
  conftest.py            # pytest fixtures (async httpx client)
  test_health.py          # health endpoint test
```

## Getting started

```bash
uv sync                        # install dependencies (creates .venv)
cp .env.example .env           # configure environment variables
uv run resumepilot             # run the API (http://localhost:8000)
```

## Development

```bash
uv run pytest                  # run tests
uv run ruff check .            # lint
uv run ruff format .           # format
```

## Docker

```bash
docker compose up --build
```

The API listens on `:8000`; health check at `GET /v1/health`.
