# Project Assurance Register

## Current status

**Phase 07 — Incremental Updates: local implementation PASS, not independently re-verified.**
Phase 06 historical independent FAIL / NO-GO and later exclusive retry-allowlist correction remain
in `PROGRESS.md`. Phase 05 historical independent FAIL / NO-GO remains in `PROGRESS.md`. Phase 03
current status is independent final follow-up GO: committed, PR #3 merged to `main` as `ceb2bf0`,
remote CI PASS (2 successful checks).

The repository now provides grounded Understand and Examine over the Phase 02 data layer, a
PostgreSQL-backed durable workflow that can survive process death, and focused incremental updates
over an immutable corpus baseline:

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
  rejected assertions are explicit; `untrusted_instruction` blocks are excluded from extraction;
- a versioned ruleset `software-project-assurance.v1` plus a LangGraph Examine workflow:
  load understanding → select rules → evaluate rules → validate evidence → summarize → finalize;
- `ExaminationRun`, `Finding`, and `ExaminationStageEvent` records with corpus isolation;
- an explicit human review gate: `ReviewSession`, `ReviewItem`, and append-only `ReviewDecision`
  records; FAIL/WARNING/UNKNOWN findings require a decision; generation never auto-approves;
- a durable workflow run (`WorkflowRun`) that coordinates Understand → Examine → human review with
  LangGraph PostgreSQL checkpoints, a costly-operation ledger, and real process-kill resume;
- focused incremental updates (`CorpusRevision`, `IncrementalRun`) that detect SHA-256 source
  changes, recompute only provenance-affected work, reuse unaffected artifacts with canonical
  unchanged-byte proof, and persist executed-versus-reused operation evidence; and
- all verified Phase 01–06 foundation capabilities.

OCR, scanned-image interpretation, handwriting, spreadsheets, arbitrary binary formats, and
internet-facing production hardening remain excluded.

**MCP business operations, register publication, and production deployment are not implemented.**

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
- LangGraph 1.2.11 (Understand, Examine, and the durable workflow graph)
- langgraph-checkpoint-postgres 3.1.2 and psycopg[binary] 3.3.4 (PostgreSQL checkpointer)
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
- `WATCH_INPUT_PATH` for the optional stable-file inbox; Compose uses `/data/watch-inbox`
- `WATCH_POLL_SECONDS`, default `2`
- `WATCH_STABLE_POLLS`, default `2`
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

Returns application version `0.7.0`, current Phase 07 metadata, and a truthful statement that
focused incremental updates and stable-file inbox watching are implemented over grounded
Understand, Examine, explicit human review, and durable resume, while MCP business operations and
register publication are not.

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
$exam = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/corpora/$($corpus.id)/analysis-runs/$($run.id)/examination-runs"
Invoke-RestMethod "http://localhost:8000/corpora/$($corpus.id)/examination-runs/$($exam.id)/summary"
$review = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/corpora/$($corpus.id)/examination-runs/$($exam.id)/review-sessions"
Invoke-RestMethod "http://localhost:8000/corpora/$($corpus.id)/review-sessions/$($review.id)/items"
```

### Phase 04 Examine API

- `POST /corpora/{corpus_id}/analysis-runs/{analysis_run_id}/examination-runs`
- `GET /corpora/{corpus_id}/examination-runs/{examination_run_id}`
- `GET /corpora/{corpus_id}/examination-runs/{examination_run_id}/findings`
- `GET /corpora/{corpus_id}/examination-runs/{examination_run_id}/summary`
- `GET /corpora/{corpus_id}/examination-runs/{examination_run_id}/stage-events`

Every operation is corpus-scoped. The analysis run must belong to the same corpus and must be
`completed`. Cross-corpus examination lookups return not found. Subject-specific rules require
both the rule's category and `subject_key`. Findings consume only Phase 03 supported facts and
grounded contradictions from the same analysis run and corpus. Retrieval hits, rejected
assertions, and raw source text cannot satisfy a rule. Missing required evidence is `unknown`,
never `pass`, and UNKNOWN findings carry no fact, contradiction, or citation evidence.
Prompt-injection source text cannot add or override a rule.

API citations are derived from referenced grounded facts after Phase 02 exact provenance and
Phase 03 assertion grounding are revalidated. They are not an independent evidence store.

`spa.contradiction.open` fails only remaining contradictions not already consumed by a more
specific rule. Zero remaining contradictions PASS only with a same-run completed
`detect_contradictions` stage attestation (process evidence, not source provenance). Unrelated
supported facts are never attached.

Ruleset `software-project-assurance.v1` is configuration data plus named evaluators. It is not
corpus-name special-casing. Outcomes are `pass`, `fail`, `warning`, and `unknown`. An examination
of a no-findings Understand run returns `findings_status=no_findings` with an empty finding list
after the applicable-rule count is evaluated as zero.

### Phase 05 Human Review API

- `POST /corpora/{corpus_id}/examination-runs/{examination_run_id}/review-sessions`
- `GET /corpora/{corpus_id}/review-sessions/{review_session_id}`
- `GET /corpora/{corpus_id}/review-sessions/{review_session_id}/items`
- `GET /corpora/{corpus_id}/review-sessions/{review_session_id}/items/{item_id}`
- `POST /corpora/{corpus_id}/review-sessions/{review_session_id}/items/{item_id}/decisions`
- `POST /corpora/{corpus_id}/review-sessions/{review_session_id}/complete`

Every operation is corpus-scoped. The examination run must belong to the same corpus and must be
`completed`. Session creation is idempotent for `(corpus_id, examination_run_id)`. One review item
is created per finding. FAIL, WARNING, and UNKNOWN items require review; PASS items are visible and
optional and do not block completion. Generation never auto-approves. Status remains
`waiting_for_review` until an explicit complete call.

Decision actions are `approve`, `reject`, and `edit`. History is append-only and the item status is
the latest valid decision. Decision and completion transactions take PostgreSQL row locks on the
review session; decisions also lock the target item. Session counts are recomputed from item rows
inside that transaction. EDIT requires non-blank reviewer-authored text and
`reviewer_authored_acknowledged=true`; the original proposed snapshot and grounded citations are
retained, and the replacement is marked not system-grounded. Approve/reject cannot carry edited
content. Phase 03/04 finding records are not mutated.

A session completes only when every required item has a terminal explicit decision. Pending required
items return `review_session_incomplete`. Cross-corpus session/item lookups return not found.
Vector scores are not evidence. The same operations are available to the React review panel and to
machine/API clients. MCP is not implemented.

### Phase 06 Durable Workflow API

- `POST /corpora/{corpus_id}/workflow-runs` — start Understand → Examine → human-review gate
- `GET /corpora/{corpus_id}/workflow-runs/{run_id}`
- `POST /corpora/{corpus_id}/workflow-runs/{run_id}/resume`
- `GET /corpora/{corpus_id}/workflow-runs/{run_id}/events`

Every operation is corpus-scoped. Cross-corpus run lookups return not found without traceback.
`checkpoint_thread_id` equals the workflow run id. Status values are `pending`, `running`,
`waiting_for_review`, `failed`, and `completed`. Failed is not waiting.

Start and resume are synchronous in the API process. A dedicated PostgreSQL session-level advisory
lock (`workflow-run:{run_id}`) covers claim, checkpoint inspect, optional failed-thread reset, graph
invoke, and final state update. Concurrent resumes of the same run serialize; `resume_count`
increments once per actual execution after that lock, not merely because a second caller arrived.
A run that reaches human review stops at `waiting_for_review`. Resume of a waiting run does not
auto-approve, create decisions, or bypass pending items. After the Phase 05 session is explicitly
completed, resume continues to `completed`. Resume of an already-completed run returns
`workflow_run_already_completed`. A pending/running run with no checkpoint re-enters the same
run/thread from canonical initial state. Publication is not performed.

Costly model calls go through a durable operation ledger. The canonical operation key is SHA-256 of
the sorted JSON of: workflow run id, stage, operation type, source-input version, canonical request
hash, model provider, model name, taxonomy version, Understand graph version, prompt/config version,
and outer workflow graph version. Timestamps and other runtime-only metadata are excluded.
Deterministic mode records zero external cost. Process-kill recovery is proven by
`tests/test_process_kill_resume.py` using `scripts/durable_workflow_worker.py`:

```text
REAL PROCESS TERMINATION → NEW PROCESS → SAME RUN → RESUME
```

```powershell
uv run pytest tests/test_process_kill_resume.py::test_real_process_kill_then_new_process_resumes_same_run
```

### Phase 07 Incremental API

- `POST /corpora/{corpus_id}/revisions` — create the first current `CorpusRevision` baseline
- `GET /corpora/{corpus_id}/revisions/current`
- `POST /corpora/{corpus_id}/incremental-runs` — detect SHA-256 source changes and run focused
  Understand/Examine/review against the current baseline
- `GET /corpora/{corpus_id}/incremental-runs/{run_id}`
- `GET /corpora/{corpus_id}/incremental-runs/{run_id}/impact`
- `GET /corpora/{corpus_id}/incremental-runs/{run_id}/evidence`
- `POST /watcher/poll` — one stable-file inbox poll when `WATCH_INPUT_PATH` is set

Every operation is corpus-scoped. Cross-corpus revision/run lookups return not found. Change
identity is logical source plus SHA-256; timestamps are not used. Identical bytes for one logical
source do not create a new `SourceVersion`. Changed bytes create a new immutable version and a new
incremental analysis/examination/review set. The previous review session is left immutable. New
review items start `pending`; prior approvals are never copied. A materially changed proposal
requires fresh explicit review.

If the supplied `baseline_revision_id` is not the current corpus revision, the run is persisted as
`stale_baseline` and the API returns HTTP 409. Same-corpus incremental execution is serialized with
`pg_advisory_lock(hashtext('incremental-corpus:{corpus_id}'))`. At most one run advances revision
N to N+1. The losing run does not apply a mixed-base result.

No-full-rerun proof is the durable evidence payload: classify **and** extract executed versus
skipped source-version IDs with per-source-version disposition (`executed` / `reused` /
`skipped`), reused versus recomputed fact/contradiction/rule IDs, completed durable
operation rows for reuse claims, skipped keys when no ledger row exists (never fabricated as
`reused`), canonical unchanged artifact hashes taken from persisted rows including review-item
before/after bytes, and stages executed/skipped from actual control flow.
Final-output equality alone is not accepted as proof. Canonical serialization is
`incremental-artifact.v1`: sorted-key compact UTF-8 JSON excluding ids, run ids, timestamps,
review session/item ids, and current decision state.

The watcher polls `{WATCH_INPUT_PATH}/{corpus_id}/{logical_name}.{ext}`. A file is eligible only
after `WATCH_STABLE_POLLS` consecutive polls with the same SHA-256 and size. Restart uses persisted
`watcher_files` rows so completed unchanged bytes are not re-ingested, while pending incremental
work is retried without creating a new SourceVersion.

```powershell
$baseline = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/corpora/$($corpus.id)/revisions" `
  -ContentType "application/json" `
  -Body (@{
    analysis_run_id = $run.id
    examination_run_id = $exam.id
    review_session_id = $review.id
  } | ConvertTo-Json)
$incremental = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/corpora/$($corpus.id)/incremental-runs" `
  -ContentType "application/json" `
  -Body (@{ baseline_revision_id = $baseline.id } | ConvertTo-Json)
Invoke-RestMethod "http://localhost:8000/corpora/$($corpus.id)/incremental-runs/$($incremental.id)/evidence"
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
uv run alembic downgrade 20260819_0006
uv run alembic upgrade head
uv run alembic current
# Schema-only. Populated 0007 → 0006 with incremental DurableOperation rows is
# `tests/test_incremental_migration.py` under pytest -m integration.

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

All three services should report healthy. `/version` should report application version `0.7.0`,
`Phase 07 — Incremental Updates`, focused incremental updates and stable-file inbox watching over
grounded Understand/Examine plus explicit human review and durable resume, and the absence of MCP
business operations and register publication. The frontend status shell includes a minimal review
panel. Human Review UI remains primary.

## CI

`.github/workflows/ci.yml` runs on pull requests to `main` and pushes to `main`.

- Backend: Python 3.13.14, frozen uv install, pgvector service, migration, Phase 07 test-database
  schema round-trip `0006 → 0007 → 0006 → 0007`, Ruff format/lint, mypy, pytest with coverage
  (includes populated `0007` downgrade with incremental ledger rows, process-kill/resume, and
  incremental Aurora/Harbor proof), and package build.
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
- Examine evaluates a centrally versioned ruleset against grounded Phase 03 facts. It is not a
  user-upload rule editor, generic expression engine, or register-publication step.
- Human review is an explicit item-level gate over Examine findings. It does not publish a register
  version or provide MCP tools.
- Durable resume is implemented for the workflow run. It does not publish approved items or run a
  separate worker fleet. The API process executes the graph; the subprocess worker exists for
  kill/resume proof.
- Local completed persistence (A): a ledger row `completed` with result hash/payload is reused and
  does not call the provider again.
- Logical idempotency (B): one logical operation per canonical key; `logical_operation_count = 1`
  after success. Provider attempts may be greater than one only under a safe retry policy.
- Provider ambiguity (C): if a live call may have executed and the local result was not stored, the
  row is `ambiguous`. Exactly-once provider execution is not claimed.
- Safe retry vs fail-closed live policy (D): the live adapter automatic retry allowlist is
  exclusive: `ConnectTimeout`, `PoolTimeout`, `ConnectError`, HTTP 429, and HTTP 503. The live
  request loop retries only a `SAFE_RETRY` disposition, not a generic `retryable` flag.
  Malformed/unusable HTTP 200 output is a terminal `model_output_invalid` and is not retried.
  `ReadTimeout`, `WriteTimeout`, unknown `TimeoutException`, HTTP 408, HTTP 504,
  `RemoteProtocolError`, and other unclassified `httpx.HTTPError` values are
  `operation_ambiguous` and are not retried. When classification is uncertain, the live path
  fails closed to `ambiguous`. Deterministic mode may reconcile `ambiguous`. Provider
  idempotency is not configured.
- Failed-stage resume is a same-run/thread restart: under the session lock it deletes only that
  thread's LangGraph checkpoint rows and re-enters from durable business/ledger state. It is not
  in-place continuation of a failed LangGraph node.
- Focused incremental updates are implemented over a durable corpus revision/baseline. They do not
  publish a register version, auto-approve review items, or treat hash equality of final outputs as
  proof that a full rerun was avoided. Source removal is recorded in the change-set planner when a
  logical source disappears from the latest version set; the watcher marks temporarily missing inbox
  files and does not delete Source/SourceVersion rows. A crash after incremental Understand/Examine/
  review rows are written but before atomic revision finalization may leave non-current orphan
  `AnalysisRun`, `ExaminationRun`, and `ReviewSession` rows. Those rows cannot become current
  revision state, are not reused as the authoritative baseline, are not deleted automatically, and
  cleanup/reconciliation is deferred. The incremental operation is therefore not globally
  rollback-clean for those pre-finalization artifacts.
- The watcher is stable-file polling of a mounted inbox. It is not inotify, watchdog, Kafka, or a
  distributed worker. Eligibility is identical SHA-256 plus size across `WATCH_STABLE_POLLS`
  polls, not filesystem mtime alone.
- MCP business operations and register publication remain unimplemented.

## Project documentation

- `TASK.md` — persistent Task 1 engineering contract
- `PROGRESS.md` — chronological decisions, commands, failures, evidence, and limitations
- `docs/architecture.md` — implemented Phase 01–07 architecture and later-phase plans
