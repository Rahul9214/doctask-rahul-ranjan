# Project Assurance Register

## Current status

**Phase 01 — Development Foundation: implemented and verified.**

This repository currently provides only the technical foundation for Task 1:

- FastAPI application lifecycle and metadata;
- database-independent `GET /health`;
- PostgreSQL and pgvector-aware `GET /ready`;
- truthful `GET /version` phase metadata;
- environment-backed, secret-safe settings;
- async SQLAlchemy engine/session setup;
- Alembic with an initial pgvector extension migration;
- a React/TypeScript status shell;
- PostgreSQL 17 + pgvector, backend, and frontend containers;
- backend/frontend quality tooling and tests; and
- pull-request/push CI for `main`.

**Task 1 business workflow is not implemented yet.**

The following remain planned for later phases and are not claimed here: document ingestion or
parsing, Project Assurance Register business records, LangGraph execution, LLM calls, human
review, durable resume, MCP business tools, incremental updates, a watcher, and production
deployment.

## Runtime and dependency baseline

- Python: **CPython 3.13.14**, managed by uv and pinned in `backend/.python-version`
- uv: **0.11.26**
- Node.js: **22.20.0** — selected runtime baseline
- npm: **11.12.1** — candidate verification version, not an enforced project-wide exact version
- PostgreSQL: **17** with pgvector **0.8.1**
- Docker image: `pgvector/pgvector:0.8.1-pg17-bookworm`

Python 3.13 was selected instead of the host's Python 3.14 to retain broad wheel and runtime
compatibility across FastAPI, SQLAlchemy, Alembic, asyncpg, LangGraph, PostgreSQL checkpointing,
pgvector, MCP, and test tooling. uv installs the project runtime without changing the global Python
installation.

Primary backend versions are locked in `backend/uv.lock`:

- FastAPI 0.141.1, Pydantic 2.13.4, pydantic-settings 2.15.0
- SQLAlchemy 2.0.52, asyncpg 0.31.0, Alembic 1.19.1
- LangGraph 1.2.11 and langgraph-checkpoint-postgres 3.1.2 (dependency only; unused in Phase 01)
- pgvector 0.5.0 (dependency only; no vector business schema yet)
- MCP 2.0.0 (dependency only; no MCP server or tools yet)
- Uvicorn 0.52.3
- Ruff 0.16.3, mypy 2.3.1, pytest 9.1.1, pytest-asyncio 1.4.0,
  pytest-cov 7.1.0, and HTTPX 0.28.1

The committed `frontend/package-lock.json` defines the dependency resolution. The direct baseline includes
React 19.2.8, Vite 8.2.1, TypeScript 6.0.3, ESLint 10.8.1, Prettier 3.9.6, Vitest 4.1.11, and React
Testing Library 16.3.2.

## Quick start

Prerequisites:

- Docker Desktop with Compose
- no model, LLM, SuperDocs, or other API key

From the repository root in PowerShell:

```powershell
docker compose up --build
```

Compose creates a persistent PostgreSQL volume, waits for database health, applies Alembic
migrations, starts the backend, and serves the built frontend through Nginx.

Open:

- frontend: <http://localhost:5173>
- backend OpenAPI: <http://localhost:8000/docs>
- liveness: <http://localhost:8000/health>
- readiness: <http://localhost:8000/ready>
- version/phase: <http://localhost:8000/version>

Stop the stack from another terminal:

```powershell
docker compose down
```

`docker compose down` preserves the database volume. Use `docker compose down --volumes` only when
you intentionally want to delete local database data.

## Configuration

`.env.example` contains safe local-only defaults. The stack runs without copying it because Compose
has matching local defaults. Copy it to `.env` only when you want overrides; `.env` is ignored by
Git.

Important variables:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_PORT`
- `BACKEND_PORT`
- `FRONTEND_PORT`
- `DATABASE_URL` for direct host-side backend commands
- `READINESS_TIMEOUT_SECONDS`

The simple Compose path is local-development only. Its `POSTGRES_PASSWORD` must match
`[A-Za-z0-9_]+` because Compose passes the same literal value to PostgreSQL and interpolates it
directly into `DATABASE_URL`. The default `local_only` satisfies this contract. Percent-encoding the
variable is not a workaround: PostgreSQL would receive the encoded text as its literal password.
Arbitrary or special-character passwords are not supported by this Compose interpolation.

## Endpoint contract

### `GET /health`

Reports application-process liveness and never contacts the database.

```json
{"status":"alive"}
```

### `GET /ready`

Returns HTTP 200 only when PostgreSQL is reachable and the `vector` extension is enabled. A
dependency failure returns HTTP 503 with safe cause and next-action fields. Driver exception text
and the configured database URL are not returned.

### `GET /version`

Returns application version, current phase, and:

```text
Task 1 business workflow is not implemented yet.
```

## Local quality commands

### Backend

Run from `backend/`:

```powershell
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv run pytest --cov=app --cov-report=term-missing
uv build
```

To apply formatting:

```powershell
uv run ruff format .
uv run ruff check --fix .
```

### Frontend

Run from `frontend/`:

```powershell
npm ci
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
```

To apply formatting:

```powershell
npm run format
```

## Database integration verification

Start the database from the repository root:

```powershell
docker compose up --detach db
```

Then run from `backend/`:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance"
$env:TEST_DATABASE_URL = $env:DATABASE_URL
uv run alembic upgrade head
uv run alembic current
uv run pytest tests/test_readiness_integration.py
```

Cleanup from the repository root:

```powershell
docker compose down
```

## Smoke checks

With the full stack running:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
Invoke-RestMethod http://localhost:8000/version
Invoke-WebRequest -UseBasicParsing http://localhost:5173/
Invoke-WebRequest -UseBasicParsing http://localhost:5173/api/ready
docker compose ps
```

All three services should report healthy. The browser UI should show `Foundation ready`, application
version `0.1.0`, `Phase 01 — Development Foundation`, and the explicit not-implemented message.

## CI

`.github/workflows/ci.yml` runs on pull requests to `main` and pushes to `main`.

- Backend: Python 3.13.14, frozen uv install, pgvector service, migration, Ruff format/lint, mypy,
  pytest with coverage, and package build.
- Frontend: Node 22.20.0, `npm ci`, Prettier, ESLint, TypeScript, Vitest, and production build.

No deployment workflow exists.

## Security posture

- No real secrets or API keys are required or committed.
- Database settings use `SecretStr`; readiness errors expose controlled messages, not driver text.
- `.env`, virtual environments, dependency directories, coverage, build output, runtime database
  files, caches, `*.log`, `logs/`, and IDE files are ignored.
- Containers use local-only defaults intended solely for development.
- No claim is made for internet-facing authentication, production hardening, certification, or
  guaranteed redaction.

## Project documentation

- `TASK.md` — persistent Task 1 engineering contract
- `PROGRESS.md` — chronological decisions, commands, failures, evidence, and limitations
- `docs/architecture.md` — planned overall architecture plus the implemented Phase 01 foundation
