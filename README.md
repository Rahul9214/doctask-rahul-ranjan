# Project Assurance Register

## Current status

**Phase 03 — Understand: local re-verification PASS after independent verification FAIL;
independent follow-up NO-GO is retained.** Independent verification found that a valid but
unrelated citation could previously support a fabricated assertion. Citation validity plus
assertion-to-evidence validation is now required. A later follow-up found failed-retry attempt
undercount and equivalent-value contradiction comparison; those corrections are in this tree.
The independent FAIL and follow-up NO-GO records are retained in `PROGRESS.md`. Independent
verification is not PASS.

The repository now provides grounded Understand over the Phase 02 data layer:

- corpus-scoped `Corpus`, `Source`, `SourceVersion`, and `SourceBlock` records that are immutable by
  application contract and API/service behavior;
- bounded streamed upload, SHA-256 content addressing, exact citation validation, and pgvector retrieval;
- a configurable model boundary (deterministic keyless adapter by default; one OpenAI-compatible live provider);
- a LangGraph Understand workflow: load → retrieve candidate blocks → classify those candidates →
  extract relevant blocks → citation resolver → assertion-to-evidence validation → contradictions →
  finalize;
- `AnalysisRun`, `Fact`, `Contradiction`, and `StageEvent` records with corpus isolation;
- no-bluffing: supported facts require a valid citation **and** a deterministic check that the
  asserted category, subject, and value are derivable from the cited quote; unknown fields and
  rejected assertions are explicit; `untrusted_instruction` blocks are excluded from extraction; and
- all verified Phase 01/02 foundation capabilities.

OCR, scanned-image interpretation, handwriting, spreadsheets, arbitrary binary formats, and
internet-facing production hardening remain excluded.

**Examine, item-level human review, durable kill/resume, MCP business operations, watching/incremental
updates, register publication, and production deployment are not implemented.**

## Runtime and dependency baseline

- Python: **CPython 3.13.14**, managed by uv and pinned in `backend/.python-version`
- uv: **0.11.26**
- Node.js: **22.20.0** — selected runtime baseline
- npm: **11.12.1** — candidate verification version, not an enforced project-wide exact version
- PostgreSQL: **17** with pgvector **0.8.1**
- Docker image: `pgvector/pgvector:0.8.1-pg17-bookworm`

Python 3.13 was selected instead of the host's Python 3.14 to retain broad wheel and runtime
compatibility. uv installs the project runtime without changing the global Python installation.

Primary backend versions are locked in `backend/uv.lock`:

- FastAPI 0.141.1, Pydantic 2.13.4, pydantic-settings 2.15.0
- SQLAlchemy 2.0.52, asyncpg 0.31.0, Alembic 1.19.1
- LangGraph 1.2.11 (Understand workflow) and langgraph-checkpoint-postgres 3.1.2 (locked, unused)
- httpx 0.28.1 (OpenAI-compatible live provider path)
- pgvector 0.5.0 (used for SQLAlchemy `vector(64)` storage and cosine queries)
- pypdf 6.16.1, python-docx 1.2.0, and python-multipart 0.0.32
- MCP 2.0.0 (locked but no MCP server or business tools yet)
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

Compose creates persistent PostgreSQL and source-file volumes, waits for database health, applies
Alembic migrations, starts the backend, and serves the built frontend through Nginx.

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

`docker compose down` preserves both volumes. Use `docker compose down --volumes` only when you
intentionally want to delete local database and uploaded source data.

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
- `TEST_DATABASE_URL`, which must name the dedicated `project_assurance_test` database
- `ALLOW_DESTRUCTIVE_TEST_DATABASE`, which must explicitly be `true` before integration cleanup
- `READINESS_TIMEOUT_SECONDS`
- `SOURCE_STORAGE_PATH` for host execution; Compose uses `/data/source-files`
- `MAX_UPLOAD_BYTES`, default **10 MiB** and constrained to at most 100 MiB by settings
- `MODEL_PROVIDER`, default `deterministic` (keyless). Set `openai` only with `OPENAI_API_KEY`
- `OPENAI_MODEL`, `OPENAI_BASE_URL`, `MODEL_TIMEOUT_SECONDS`, `MODEL_MAX_RETRIES`

Do not commit `OPENAI_API_KEY`. The default Compose/test path requires no model key.

Integration cleanup is denied before `TRUNCATE` unless the test URL names
`project_assurance_test`, differs from the application database name, and the destructive-test
opt-in is `true`.

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

Returns application version `0.3.0`, current Phase 03 metadata, and a truthful statement that
grounded Understand is implemented while Examine, human review, durable resume, MCP business
operations, and watching are not.

### Phase 02 corpus and source API

- `POST /corpora`
- `GET /corpora/{corpus_id}`
- `POST /corpora/{corpus_id}/sources` — multipart `logical_name`, `declared_format`, and `file`
- `GET /corpora/{corpus_id}/sources`
- `GET /corpora/{corpus_id}/sources/{source_id}`
- `GET /corpora/{corpus_id}/source-versions/{version_id}`
- `GET /corpora/{corpus_id}/source-versions/{version_id}/blocks`
- `POST /corpora/{corpus_id}/citations/validate`
- `POST /corpora/{corpus_id}/search`

Every operation is corpus-scoped. Cross-corpus source/version/citation lookups return not found.
Repeated identical bytes for one logical source return the existing version; changed bytes create
a new version. `SourceVersion` and `SourceBlock` are immutable by application contract and
API/service behavior. Database mutation-prevention triggers and restricted mutation roles are not
implemented.

The upload endpoint has two bounds: an HTTP request-size guard rejects a declared `Content-Length`
above `MAX_UPLOAD_BYTES` plus 1 MiB of multipart overhead before normal multipart parsing, and the
streamed file-content bound enforces `MAX_UPLOAD_BYTES` while reading `UploadFile`. If
`Content-Length` is absent or transfer is chunked, only the authoritative streamed file-content
bound applies.

An example container-side TXT ingestion from the repository root:

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

### Phase 03 Understand API

- `POST /corpora/{corpus_id}/analysis-runs` — run Understand synchronously
- `GET /corpora/{corpus_id}/analysis-runs/{run_id}`
- `GET /corpora/{corpus_id}/analysis-runs/{run_id}/facts`
- `GET /corpora/{corpus_id}/analysis-runs/{run_id}/contradictions`
- `GET /corpora/{corpus_id}/analysis-runs/{run_id}/understanding`
- `GET /corpora/{corpus_id}/analysis-runs/{run_id}/stage-events`

Every operation is corpus-scoped. Cross-corpus run lookups return not found. Supported facts include
a Phase 02 citation that has already passed exact provenance validation **and** assertion-to-evidence
validation against the resolved quote. Unknown inspection fields use `support_status=unknown` and
`normalized_value=INSUFFICIENT_EVIDENCE`. Retrieval selected context is classified; it is not itself
evidence. If retrieval returns no candidates for a non-empty corpus, Understand records
`retrieval_mode=fallback_full_corpus` and classifies a bounded full-corpus set.

Default execution uses `MODEL_PROVIDER=deterministic` and records zero external model cost.
`model_operation_count` is logical model operations; `model_attempt_count` is provider HTTP attempts.
Skipped stages persist `status=skipped` with `model_operation_count=0`, `model_attempt_count=0`,
and `estimated_cost_usd=0`. Implemented skip reasons: `empty_corpus`, `no_relevant_blocks`,
`retrieval_empty_fallback`, and `prior_stage_failed`.

```powershell
$run = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/corpora/$($corpus.id)/analysis-runs"
Invoke-RestMethod "http://localhost:8000/corpora/$($corpus.id)/analysis-runs/$($run.id)/understanding"
```

### Normalization and exact provenance

Original bytes are written under generated version keys and treated as immutable by application
contract. Markdown/TXT decode as UTF-8, line endings become LF, Unicode becomes NFC, non-breaking
spaces become regular spaces, trailing whitespace is removed per line, and blank boundary lines
are removed. PDF/DOCX extracted text uses the same block normalizer.

A citation contains `source_version_id`, `source_sha256`, `format`, `native_locator`, a half-open
`normalized_start:normalized_end` character span within the normalized block, and `exact_quote`.
The resolver re-hashes stored bytes, reparses the registered format from those bytes, resolves the
locator against the fresh parse, verifies persisted block integrity, bounds-checks the fresh span,
and compares the exact quote. Vector similarity and persisted block text alone never validate
evidence.

Locator forms:

- PDF: `page[1]/block[0]`
- DOCX: `paragraph[0]` or `table[0]/row[0]/cell[0]/paragraph[0]`
- Markdown/TXT: `lines[1-3]/block[0]`

### Deterministic embeddings

The local adapter tokenizes with the pinned Python runtime, hashes tokens with SHA-256 into 64
signed dimensions, and L2-normalizes the vector. It requires no key and gives stable local/test
retrieval behavior. It is not an LLM embedding and must not be described as model-quality semantic
retrieval.

## Local quality commands

### Backend

Run from `backend/`:

```powershell
uv sync --frozen --all-groups
uv run python scripts/generate_synthetic_corpora.py
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv build
```

The full coverage suite includes PostgreSQL/pgvector integration, so set the database variables as
shown below before running pytest.

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
$appDatabaseUrl = "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance"
$testDatabaseUrl = "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance_test"
$env:DATABASE_URL = $appDatabaseUrl
uv run python scripts/ensure_test_database.py
uv run alembic upgrade head

$env:DATABASE_URL = $testDatabaseUrl
uv run alembic upgrade head
uv run alembic downgrade 20260819_0001
uv run alembic upgrade head
uv run alembic current

$env:DATABASE_URL = $appDatabaseUrl
$env:TEST_DATABASE_URL = $testDatabaseUrl
$env:ALLOW_DESTRUCTIVE_TEST_DATABASE = "true"
uv run pytest -m integration
uv run pytest --cov=app --cov-report=term-missing
```

The guard intentionally refuses `TEST_DATABASE_URL = DATABASE_URL`. The test database is
disposable; the application database is not.

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

All three services should report healthy. `/version` should report application version `0.3.0`,
`Phase 03 — Understand`, grounded Understand, and the absence of Examine/review/resume/MCP watching.
The existing frontend remains a dependency/status shell.

## CI

`.github/workflows/ci.yml` runs on pull requests to `main` and pushes to `main`.

- Backend: Python 3.13.14, frozen uv install, pgvector service, migration, Ruff format/lint, mypy,
  pytest with coverage, and package build.
- Frontend: Node 22.20.0, `npm ci`, Prettier, ESLint, TypeScript, Vitest, and production build.

No deployment workflow exists.

## Security posture

- No real secrets or API keys are required or committed. `OPENAI_API_KEY` is optional and only used
  when `MODEL_PROVIDER=openai`.
- Database settings use `SecretStr`; readiness and model errors expose controlled messages, not
  driver text, source content, or credentials.
- Document text is stored and indexed as untrusted data; it is never an instruction or evidence
  merely because a vector query returned it. Source sentences that attempt to override instructions
  are classified as data and cannot disable provenance or fabricate compliance.
- Citation validation rejects wrong hashes, locators, spans, quotes, tampered bytes, missing
  versions, persisted-block tampering, and cross-corpus lookups by reparsing original bytes.
  Model output cannot override that validator.
- Upload size is bounded; client filenames cannot provide path components; storage keys are
  generated; partial staging files are removed on failure.
- Upload protection is an HTTP request-size guard plus a streamed file-content bound; requests
  without usable `Content-Length` rely on streaming enforcement.
- PDF signature/text extraction and DOCX ZIP structure, entry count, expanded size, per-entry size,
  and compression ratio are checked before successful ingestion.
- Supported/common malformed-input classes exercised by the test suite return controlled
  cause/remedy errors. Exhaustive malformed-input containment is not claimed.
- `.env`, virtual environments, dependency directories, coverage, build output, runtime database
  files, caches, `*.log`, `logs/`, and IDE files are ignored.
- Containers use local-only defaults intended solely for development.
- No claim is made for internet-facing authentication, production hardening, certification, or
  guaranteed redaction.

## Current limitations

- PDF support is extractable text only; no OCR or scanned-image interpretation exists.
- The pypdf parser has an upload-size bound but no separate process sandbox or parse-time timeout.
- Parser isolation and exhaustive malformed-input containment remain deferred.
- DOCX support covers normal body paragraphs and table-cell paragraphs. Complex drawing text,
  headers/footers, comments, and merged/nested-table fidelity are not claimed.
- Markdown parsing intentionally covers deterministic headings, lists, and paragraph blocks rather
  than full rendering semantics.
- Local hashed feature vectors are lexical retrieval aids, not semantic LLM embeddings.
- Local/container file storage is durable through a named volume but is not object storage,
  replicated storage, malware scanning, or production document management.
- A process crash after file promotion but before database commit can leave an orphan. Cancellation
  edge cases require later reconciliation, and cleanup failures are best-effort.
- The API has no internet-facing authentication/authorization layer; corpus identity is the current
  isolation boundary.
- The live OpenAI-compatible path is optional; executable evidence uses the deterministic adapter.
  That adapter is a compact rule/regex Software Project Assurance extractor with intentionally
  limited linguistic coverage. It is not general-purpose semantic reasoning. All provider output,
  including the live path, still passes citation resolution and assertion-to-evidence validation.
  Live-path cost is reported as unavailable unless a pricing snapshot is added later.
- Contradiction detection is deterministic over supported facts that share category and subject key.
  Subtle semantic conflicts outside that contract are not claimed.
- Examine, human review, durable resume, MCP business operations, watching, and register
  publication remain unimplemented.
- LangGraph PostgreSQL checkpoint/interrupt behavior is not used in Phase 03.

## Project documentation

- `TASK.md` — persistent Task 1 engineering contract
- `PROGRESS.md` — chronological decisions, commands, failures, evidence, and limitations
- `docs/architecture.md` — implemented Phase 01–03 architecture and later-phase plans
