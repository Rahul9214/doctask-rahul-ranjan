# Project Assurance Register

Grounded software-project assurance over mixed documents: ingest an immutable corpus, Understand
facts with exact citations, Examine a versioned ruleset, wait for explicit human review, resume a
durable workflow, and **publish an approved-only register** only after that review is completed.

Application version **1.0.0**. Current phase: **Phase 10 — Final Delivery**.

Hosted cloud deployment is not implemented. MCP is local-development / trusted-client stdio with
corpus isolation and no production authentication. Generation never auto-approves or auto-publishes.
Workflow status `completed` is not publication.

Historical phase logs live in `PROGRESS.md`. This file is the operational runbook.

## Architecture

```text
source bytes
  → immutable SourceVersion (SHA-256, native locators)
  → Understand (grounded facts / UNKNOWN / contradictions)
  → Examine (versioned ruleset software-project-assurance.v1)
  → WAITING_FOR_REVIEW (explicit approve / reject / edit)
  → durable resume (PostgreSQL LangGraph checkpoints + operation ledger)
  → incremental watched updates (focused reprocess, canonical reuse proof)
  → MCP and React as adapters over the same ApplicationServices
  → explicit POST publish → immutable published register
```

Evidence boundary: supported claims require a Phase 02 citation that still resolves against stored
bytes **and** a Phase 03 assertion-to-evidence check. Reviewer-authored edits are stored and
published as REVIEWER-AUTHORED overlays; they are never presented as system-grounded quotes.
Rejected items are omitted from the published item list. Pending optional PASS findings are omitted
and are not treated as approved.

Local runtime is Docker Compose: PostgreSQL 17 + pgvector, FastAPI backend (Alembic on start),
Nginx-served React frontend.

## Prerequisites

- Docker Desktop with Compose
- no model, LLM, SuperDocs, or other API key for the default path

Optional host-side verification: uv **0.11.26**, CPython **3.13.14**, Node.js **22.20.0**.

## One-command startup

From the repository root:

```powershell
docker compose up --build
```

Compose creates persistent PostgreSQL, source-file, and watch-inbox volumes, waits for database
health, applies Alembic to head `20260822_0008`, starts the backend, and serves the built frontend
through Nginx.

Open:

- frontend: <http://localhost:5173>
- backend OpenAPI: <http://localhost:8000/docs>
- liveness: <http://localhost:8000/health>
- readiness: <http://localhost:8000/ready>
- version/phase: <http://localhost:8000/version>

Stop:

```powershell
docker compose down
```

`docker compose down` preserves volumes. Use `docker compose down --volumes` only when you
intentionally want to delete local database and uploaded source data.

## Environment variables

`.env.example` documents settings. Compose runs without copying it. Copy to `.env` only for
overrides; `.env` is Git-ignored.

**Required** for Compose / host databases:

- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`
- `BACKEND_PORT`, `FRONTEND_PORT`
- `DATABASE_URL` for host-side backend commands
- `TEST_DATABASE_URL` (must name `project_assurance_test` and differ from `DATABASE_URL`)
- `ALLOW_DESTRUCTIVE_TEST_DATABASE` must be `true` before integration cleanup

**Optional** local development: `MAX_UPLOAD_BYTES`, `READINESS_TIMEOUT_SECONDS`,
`SOURCE_STORAGE_PATH`, `WATCH_INPUT_PATH`, `WATCH_POLL_SECONDS`, `WATCH_STABLE_POLLS`,
`RULESET_PATH`.

**Live model optional:** default `MODEL_PROVIDER=deterministic` requires no key. Set
`MODEL_PROVIDER=openai` only with `OPENAI_API_KEY` (do not commit it). Also `OPENAI_MODEL`,
`OPENAI_BASE_URL`, `MODEL_TIMEOUT_SECONDS`, `MODEL_MAX_RETRIES`.

Compose `POSTGRES_PASSWORD` must match `[A-Za-z0-9_]+`. Default `local_only` satisfies the
contract. Percent-encoding is not a workaround.

## Ingest a demo corpus

With the stack running, from the repository root:

```powershell
$corpus = Invoke-RestMethod -Method Post -Uri http://localhost:8000/corpora `
  -ContentType "application/json" `
  -Body (@{
    name = "Aurora Control Hub"
    domain = "software-project-assurance"
    declared_formats = @("pdf", "docx", "markdown", "txt")
  } | ConvertTo-Json)

curl.exe --fail -X POST `
  -F "logical_name=Decision Log" `
  -F "declared_format=txt" `
  -F "file=@backend/fixtures/corpora/aurora-control-hub/decision-log.txt;type=text/plain" `
  "http://localhost:8000/corpora/$($corpus.id)/sources"
```

Repeat for the other Aurora files in `backend/fixtures/corpora/aurora-control-hub/` using the
logical names in `manifest.json` (`Project Charter` pdf, `Weekly Status Report` docx,
`Risk Register` markdown). Harbor uses `backend/fixtures/corpora/harbor-ledger-modernization/`
with the same APIs and no corpus-name special cases.

A full Aurora+Harbor HTTP path against a live stack:

```powershell
uv run --directory backend python scripts/final_runtime_acceptance.py http://localhost:8000
```

## Run the workflow

```powershell
$run = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/corpora/$($corpus.id)/workflow-runs"
$run.status   # waiting_for_review after Understand + Examine
$run.review_session_id
```

Understand and Examine also have direct APIs if you are not using the outer workflow:

- `POST /corpora/{corpus_id}/analysis-runs`
- `POST /corpora/{corpus_id}/analysis-runs/{analysis_run_id}/examination-runs`

## Review

FAIL, WARNING, and UNKNOWN items require an explicit decision. PASS items are optional and do not
block completion. Generation never auto-approves.

```powershell
Invoke-RestMethod "http://localhost:8000/corpora/$($corpus.id)/review-sessions/$($run.review_session_id)/items"

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/corpora/$($corpus.id)/review-sessions/$($run.review_session_id)/items/<item-id>/decisions" `
  -ContentType "application/json" `
  -Body (@{ action = "approve"; decision_source = "api" } | ConvertTo-Json)

# reject:  @{ action = "reject"; decision_source = "api" }
# edit:    @{ action = "edit"; edited_content = "..."; reviewer_authored_acknowledged = $true; decision_source = "api" }

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/corpora/$($corpus.id)/review-sessions/$($run.review_session_id)/complete"
```

The React shell at `/` has the review panel plus workflow status and a compact published-register
panel. Use those instead of curl if you prefer a UI.

## Resume

After required decisions and `complete`, resume the waiting workflow:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/corpora/$($corpus.id)/workflow-runs/$($run.id)/resume"
```

Resume of `waiting_for_review` does not auto-approve. A completed workflow is still unpublished
until the explicit publish call below.

Process-kill recovery is proven by `tests/test_process_kill_resume.py`.

## Publish / finalize the register

```powershell
# Must 404 until an explicit publish:
Invoke-RestMethod "http://localhost:8000/corpora/$($corpus.id)/register"

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/corpora/$($corpus.id)/review-sessions/$($run.review_session_id)/publish" `
  -ContentType "application/json" `
  -Body (@{ actor = "reviewer"; publication_source = "api" } | ConvertTo-Json)

Invoke-RestMethod "http://localhost:8000/corpora/$($corpus.id)/register"
```

Idempotent republish of the same completed session returns the same publication (HTTP 200).
Wrong-corpus or pending-review publish is rejected. Older publications remain; one row is
`is_current`.

Before creating an authoritative row, `PublicationService` reloads each applied finding and
reuses the Examine evidence boundary: every referenced SUPPORTED fact passes Phase 02 exact
citation resolution against freshly hashed/re-parsed immutable bytes, then Phase 03 assertion
grounding. Contradictions revalidate both fact sides. Any mismatch fails closed as
`publication_evidence_validation_failed`; no current publication is advanced.

## Inspect provenance and usage

- Facts/findings: `GET .../understanding`, `GET .../findings`, review item citations
- Published items: `content_origin` is `system_grounded` or `mixed`; `system_grounded` /
  `reviewer_authored` flags; `exact_quote` + `native_locator` + `source_logical_name`
- Stage timing / tokens / honest cost: `GET /corpora/{corpus_id}/workflow-runs/{run_id}/usage`.
  `total_duration_ms` sums only non-overlapping outer workflow events
  (`duration_basis=outer_workflow_events`); Understand and Examine timings remain a separate
  nested breakdown and are not added into that total.

Default deterministic adapter: `estimated_cost_usd` is 0 with `cost_basis=zero_deterministic` and
an explicit pricing-basis sentence. Live-path cost is `unavailable` unless a pricing snapshot is
configured.

## MCP

```powershell
python -m app.mcp_server
docker compose exec backend python -m app.mcp_probe
```

Typed tools (20), all delegated to the same services as HTTP:

- inspect: `list_corpora`, `get_corpus`, `list_sources`, `get_workflow_status`, `get_understanding`,
  `get_examination`, `open_review`, `list_review_items`, `get_current_revision`,
  `get_incremental_evidence`, `get_current_register`, `get_register`
- mutate: `start_workflow`, `resume_workflow`, `approve_review_item`, `reject_review_item`,
  `edit_review_item`, `complete_review`, `publish_register`, `start_incremental_run`

`complete_review` does not publish. `publish_register` is a separate mutation (`actor="mcp"`,
`publication_source="api"`). No shell or arbitrary file execution tools exist.

## Incremental watcher

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/corpora/$($corpus.id)/revisions" `
  -ContentType "application/json" `
  -Body (@{
    analysis_run_id = $analysis.id
    examination_run_id = $exam.id
    review_session_id = $review.id
  } | ConvertTo-Json)

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/corpora/$($corpus.id)/incremental-runs" `
  -ContentType "application/json" `
  -Body (@{ baseline_revision_id = $baseline.id } | ConvertTo-Json)

Invoke-RestMethod -Method Post http://localhost:8000/watcher/poll
```

Inbox layout: `{WATCH_INPUT_PATH}/{corpus_id}/{logical_name}.{ext}`. A file is eligible only after
`WATCH_STABLE_POLLS` consecutive polls with the same SHA-256 and size.

## Ruleset configuration

`ApplicationServices` resolves `Settings.ruleset_path` during service construction and injects
that loaded ruleset into `ExamineService` / `ExamineWorkflow`; no import-time environment lookup
selects the active ruleset. Workflow metadata and incremental impact/re-evaluation use that same
injected ruleset instance, avoiding fallback to packaged module globals. The default is
`backend/src/app/rulesets/software-project-assurance.v1.json`. Changing supported outcome maps in
that JSON (or a valid `RULESET_PATH`) changes real Examine behavior without rewriting evaluator
Python. In Compose, an override path must be a path visible inside the backend container.
Executable proof:
`tests/test_ruleset.py::test_ruleset_path_changes_real_application_examine_behavior`.

## Tests

Backend, from `backend/`, with PostgreSQL reachable:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance"
$env:TEST_DATABASE_URL = "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance_test"
$env:ALLOW_DESTRUCTIVE_TEST_DATABASE = "true"
uv sync --frozen --all-groups
uv run python scripts/ensure_test_database.py
uv run alembic upgrade head
$env:DATABASE_URL = $env:TEST_DATABASE_URL
uv run alembic upgrade head
$env:DATABASE_URL = "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance"
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest --cov=app --cov-report=term-missing
uv build
```

Frontend, from `frontend/`:

```powershell
npm ci
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
```

Coverage fail-under is 90%. No paid model API is required.

## API surface (compact)

Foundation: `GET /health`, `GET /ready`, `GET /version`.

Corpus/source: `POST/GET /corpora`, sources, versions, blocks, `POST .../citations/validate`,
`POST .../search`.

Understand / Examine / review / workflow / incremental as in prior phases, plus:

- `POST /corpora/{corpus_id}/review-sessions/{review_session_id}/publish`
- `GET /corpora/{corpus_id}/register`
- `GET /corpora/{corpus_id}/register/{publication_id}`
- `GET /corpora/{corpus_id}/workflow-runs/{run_id}/usage`

Every business operation is corpus-scoped. Cross-corpus lookups return not found without traceback.

## Runtime and dependency baseline

- Python: **CPython 3.13.14** (`backend/.python-version`), uv **0.11.26**
- Node.js: **22.20.0**, npm **11.12.1** (verification version)
- PostgreSQL **17** / pgvector **0.8.1** (`pgvector/pgvector:0.8.1-pg17-bookworm`)
- FastAPI 0.141.1, SQLAlchemy 2.0.52, Alembic 1.19.1, LangGraph 1.2.11, MCP 2.0.0
- React 19.2.8, Vite 8.2.1, TypeScript 6.0.3 — see `frontend/package-lock.json`

## Smoke checks

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
Invoke-RestMethod http://localhost:8000/version
Invoke-WebRequest -UseBasicParsing http://localhost:5173/
Invoke-WebRequest -UseBasicParsing http://localhost:5173/api/ready
docker compose exec backend alembic current
docker compose exec backend python -m app.mcp_probe
docker compose ps
```

`/version` reports `1.0.0` and `Phase 10 — Final Delivery`. Alembic current is `20260822_0008`.

## CI

`.github/workflows/ci.yml` on pull requests and pushes to `main`:

- Backend: frozen uv sync, test-database bootstrap, Alembic head, 0008↔0007 schema round-trip,
  Ruff, mypy, pytest coverage, secret-pattern regression, process-kill, MCP stdio E2E,
  publication/final-acceptance E2E, `uv build`
- Frontend: `npm ci`, format, lint, typecheck, tests, build

No paid model API. No deployment workflow. No Kubernetes.

## Security posture

- No real secrets required or committed. `.env` is ignored.
- Readiness and MCP errors are controlled: no driver traceback, source dumps, or credentials.
- Document text is untrusted data. It cannot alter policy, call tools, self-approve, or publish.
- Publication requires a completed same-corpus review session.
- MCP has no arbitrary shell/file execution tools.

This is not a penetration test or certification claim.

## Known limitations

- PDF is extractable text only; no OCR, handwriting, or scanned-image interpretation.
- Spreadsheets and arbitrary binary formats are out of scope.
- No internet-facing authentication, RBAC, or hosted cloud deployment.
- Compose images run as the image default user because named volumes are written at runtime.
- Deterministic adapter is keyless and domain-narrow; it is not general LLM reasoning.
- Live-path estimated cost is unavailable without a pricing snapshot.
- Contradiction detection is deterministic over supported facts sharing category and subject key.
- Incremental watcher is stable-file polling, not inotify/Kafka.
- A crash after file promotion but before database commit can leave an orphan object.
- Deliverable-side register locators (`register_version_id` / `register_item_id`) are defined for
  later findings-about-registers; this delivery publishes source-grounded reviewed items and does
  not run a second Examine pass over the published register.
- Independent verification of this Phase 10 working tree is not claimed until performed.

## Project documentation

- `TASK.md` — assignment contract
- `PROGRESS.md` — chronological decisions and evidence
- `docs/architecture.md` — implemented architecture
- `docs/final-acceptance.md` — executable final-flow evidence
- `docs/measurements/phase-09-local.json` — recorded local measurement sample
