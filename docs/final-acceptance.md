# Final acceptance evidence

Concise executable record for Phase 10 local delivery. Independent verification is not claimed.
Do not paste thousands of test lines here.

## Aurora

Command:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance"
$env:TEST_DATABASE_URL = "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance_test"
$env:ALLOW_DESTRUCTIVE_TEST_DATABASE = "true"
uv run pytest tests/test_final_acceptance.py tests/test_publication_api.py tests/test_publication_integration.py -v --tb=short
```

Expected business outcome:

- Workflow stops at `waiting_for_review`.
- Mixed approve / reject / edit, then complete, then resume to `completed`.
- `GET /register` is 404 until explicit `POST .../publish`.
- Approved `spa.milestone.production-readiness` retains both `2026-10-30` and `2026-11-14`
  quotes attributed to `Project Charter` and `Weekly Status Report`.
- Rejected rule ids are listed in `omitted_rejected_rule_ids` and absent from `items`.
- Edited items are `content_origin=mixed` and not `system_grounded`.
- Immediately before persistence, every applied fact passes Phase 02 exact citation resolution
  against immutable bytes plus Phase 03 assertion grounding; contradiction evidence validates
  both sides.

Local result: PASS (`test_final_acceptance.py`, `test_publication_api.py`).

## Harbor

Same test as Aurora (`test_final_aurora_and_harbor_acceptance_with_isolation`).

Expected:

- Distinct publication ids and evidence.
- No `Aurora Control Hub`, `Elena Marlow`, `Project Charter`, `Weekly Status Report`,
  `2026-10-30`, or `2026-11-14` leakage into Harbor.
- Cross-corpus `GET /corpora/{harbor}/register/{aurora_publication_id}` → 404.
- Harbor required items are largely UNKNOWN; published Harbor may be
  `register_status=insufficient_evidence` rather than a false PASS.

Current configured local result: PASS. Independent PASS is not claimed.

## Prompt injection

```powershell
uv run pytest tests/test_adversarial_injection.py -v --tb=short
```

Expected: document instruction-attacks cannot add rules, call tools, self-approve, or publish.

Local result: included in full suite 229 passed.

## No bluffing

```powershell
uv run pytest tests/test_adversarial_no_bluffing.py tests/test_publication_api.py::test_empty_corpus_publication_is_honest_no_findings -v
```

Expected: unsupported stays unsupported; empty corpus publishes `no_findings` with zero items, not PASS.

Local result: PASS.

## Provenance

```powershell
uv run pytest tests/test_adversarial_provenance.py tests/test_grounding.py -v
```

Expected: citations resolve against immutable bytes; post-review citation JSON, bytes, block
binding, and contradiction-side tamper all stop explicit publication with
`publication_evidence_validation_failed`, create no register, and leak no source content.

Local result: included in full suite.

## Explicit review

```powershell
uv run pytest tests/test_review_integration.py tests/test_adversarial_review.py -v
```

Expected: no auto-approve; mixed decisions; edit requires acknowledgement.

Local result: included in full suite.

## Process kill / resume

```powershell
uv run pytest tests/test_process_kill_resume.py -v
```

Expected: new process resumes the same run without duplicating completed ledger work.

Local result: PASS in full suite.

## Incremental no-full-rerun

```powershell
uv run pytest tests/test_incremental_integration.py tests/test_adversarial_incremental.py -v
```

Expected: affected vs preserved IDs, executed vs reused operations, canonical hashes — not output equality alone.

Local result: included in full suite.

## MCP

```powershell
uv run pytest tests/test_mcp_e2e.py -v
```

Expected: Aurora and Harbor machine review both execute
start → decisions → complete → resume → completed → explicit publish → get register;
`complete_review` does not publish; cross-corpus register denial and publication-tamper errors are
controlled with no traceback/sentinel leak.

Local result: PASS (6 tests).

## Final publication / output

```powershell
uv run pytest tests/test_publication_api.py tests/test_publication_integration.py tests/test_publication_integrity.py tests/test_publication_concurrency.py tests/test_publication_migration.py -v
```

Expected:

- pending review publish rejected
- wrong corpus/session rejected
- post-completion mutation rejected
- identical republish idempotent
- concurrent same-session one register
- concurrent same-corpus one `is_current`
- post-review evidence tamper fails before authoritative persistence
- an unrelated same-corpus workflow cannot be attached to a publication from a different chain
- cross-corpus fact and contradiction publication evidence raise database `IntegrityError`
- same-corpus wrong review-item/finding, examination/analysis, and revision/publication chains
  raise database `IntegrityError`
- 0008 downgrade drops publication tables and upgrade restores empty schema

Current configured local result: PASS. Independent PASS is not claimed.

## Runtime ruleset and duration semantics

`Settings.ruleset_path` is resolved during `ApplicationServices` construction and injected into
`ExamineService` / `ExamineWorkflow`. The application-level proof changes the configured Amber
outcome and observes the changed real Examine finding while the packaged default remains Warning.

Workflow usage reports `duration_basis=outer_workflow_events`; `total_duration_ms` sums only outer
workflow events. Nested Understand/Examine durations remain visible but are not added again.

## Deployment smoke

One verified stranger command:

```powershell
docker compose up --build
```

Then:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
Invoke-RestMethod http://localhost:8000/version
Invoke-WebRequest -UseBasicParsing http://localhost:5173/
Invoke-WebRequest -UseBasicParsing http://localhost:5173/api/ready
docker compose exec backend alembic current
docker compose exec backend python -m app.mcp_probe
uv run --directory backend python scripts/final_runtime_acceptance.py http://localhost:8000
docker compose restart backend
```

Expected: version `1.0.0` / Phase 10, Alembic `20260822_0008`, MCP tools include publication,
Aurora+Harbor live publish, state survives backend restart.

Local Docker result: PASS on 2026-08-22 after `docker compose down -v` (disposable local demo
volumes removed, then new volumes created). Backend package build `1.0.0`, backend Docker image
build, and frontend Docker image build passed. Database/backend/frontend were healthy; `/health`
returned `alive`; `/ready` returned `ready` with pgvector 0.8.1; `/version` returned `1.0.0` /
`Phase 10 — Final Delivery`; frontend `/` and `/api/ready` returned 200; Alembic reported
`20260822_0008 (head)`; MCP probe reported 20 tools with `expected_present=true`.

`scripts/final_runtime_acceptance.py` passed. Aurora reported `register_status=populated`,
`applied_count=3`, omitted rejected `spa.ownership.budget`, and deterministic zero cost basis.
Harbor reported `register_status=insufficient_evidence`, `applied_count=3`, omitted rejected
`spa.dependency.evidence`, and deterministic zero cost basis. `cross_corpus_denied=true`. Backend
restart passed and `/ready` passed after restart. Run/publication UUIDs are sample-specific and
omitted. Volumes were retained after that proof.

The live script asserts, rather than merely reports, `cost_basis=zero_deterministic` and
`estimated_cost_usd=0.0` for both corpora. It also captures the rule it actually rejects from each
review response, then asserts that exact rule is listed as omitted and absent from published items.

## Backend quality gate (this working tree)

Chronological local evidence:

1. Initial Phase 10 result: 229 passed, coverage 91.24%, plus package build.
2. Historical blocked correction run: PostgreSQL unavailable; 119 passed, 117
   database-dependent skipped, coverage 50.21%, and the 90% gate failed. Migration, configured
   integration/MCP, live HTTP, restart, and Docker runtime gates were blocked at that time.
3. Later configured run with `DATABASE_URL`, `TEST_DATABASE_URL`, and
   `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`: 238 collected, 238 passed, 0 failed, coverage 91.29%.
   Ruff format/lint, mypy, and `uv build` (`project_assurance_register-1.0.0`) passed.

The third result is the current final local backend result. Independent PASS is not claimed.
