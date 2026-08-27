# Task-1 manual test playbook

This playbook proves the shipped Task-1 behavior without requiring the evaluator to read test
source. Run PowerShell commands from the repository root unless a step says otherwise. Keep the
generated IDs in the variables shown; all demo data is synthetic.

## A. Prerequisites

**Action**

```powershell
docker version
docker compose version
uv --version
node --version
```

**Expected:** Docker Desktop is running. Optional host checks use uv 0.11.26, CPython 3.13, and
Node 22. **Proves:** the documented local/container toolchain is available.

## B. Clean startup

**Action**

```powershell
docker compose down
docker compose up --build --detach
docker compose ps
```

**Expected:** `db`, `backend`, and `frontend` become healthy. Existing named volumes are retained.
**Proves:** reproducible Compose startup without deleting prior durable state.

## C. Health, readiness, and version

**Action**

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
Invoke-RestMethod http://localhost:8000/version
Invoke-WebRequest -UseBasicParsing http://localhost:5173/
docker compose exec backend alembic current
```

**Expected:** liveness is `alive`; readiness is `ready` with PostgreSQL and pgvector; version is
`1.0.0` / `Phase 10 — Final Delivery`; frontend is HTTP 200; Alembic is
`20260822_0008 (head)`. **Proves:** bounded dependency readiness, truthful versioning, built
frontend delivery, and migration head.

## D. Aurora ingestion

**Action**

```powershell
$base = "http://localhost:8000"
$corpus = Invoke-RestMethod -Method Post -Uri "$base/corpora" -ContentType "application/json" -Body (@{
  name = "Aurora Control Hub Manual"
  domain = "software-project-assurance"
  declared_formats = @("pdf", "docx", "markdown", "txt")
} | ConvertTo-Json)

$uploads = @(
  @{ logical = "Project Charter"; format = "pdf"; path = "backend/fixtures/corpora/aurora-control-hub/project-charter.pdf"; type = "application/pdf" },
  @{ logical = "Weekly Status Report"; format = "docx"; path = "backend/fixtures/corpora/aurora-control-hub/status-report.docx"; type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
  @{ logical = "Risk Register"; format = "markdown"; path = "backend/fixtures/corpora/aurora-control-hub/risk-register.md"; type = "text/markdown" },
  @{ logical = "Decision Log"; format = "txt"; path = "backend/fixtures/corpora/aurora-control-hub/decision-log.txt"; type = "text/plain" }
)
foreach ($upload in $uploads) {
  curl.exe --fail -sS -X POST `
    -F "logical_name=$($upload.logical)" `
    -F "declared_format=$($upload.format)" `
    -F "file=@$($upload.path);type=$($upload.type)" `
    "$base/corpora/$($corpus.id)/sources"
}
Invoke-RestMethod "$base/corpora/$($corpus.id)/sources"

$analysis = Invoke-RestMethod -Method Post -Uri "$base/corpora/$($corpus.id)/analysis-runs"
$examination = Invoke-RestMethod -Method Post -Uri "$base/corpora/$($corpus.id)/analysis-runs/$($analysis.id)/examination-runs"
Invoke-RestMethod -Method Post -Uri "$base/corpora/$($corpus.id)/revisions" -ContentType "application/json" -Body (@{
  analysis_run_id = $analysis.id
  examination_run_id = $examination.id
} | ConvertTo-Json)
Invoke-RestMethod "$base/corpora/$($corpus.id)/revisions/current"
```

**Expected:** four logical sources with immutable source-version IDs and SHA-256 values, then a current durable revision. A corpus is not workflow-runnable until that revision exists. Starting a workflow without it returns `corpus_revision_required` and does not create a failed run.

For the two canonical demo corpora (`Aurora Control Hub` and `Harbor Ledger Modernization`), the idempotent alternative from `backend/` is:

```powershell
uv run python scripts/bootstrap_demo_corpora.py
```

That command creates missing demo corpora, ingests fixture sources without duplicates, creates the initial current revision, skips already-correct corpora, and repairs incomplete legacy demo corpora. It does not complete human review or start a workflow run.
**Proves:** mixed-format bounded ingestion, document typing, immutable versioning, corpus scope, and the initial current revision required before Start workflow.

## E. Start the durable workflow

**Action**

```powershell
$run = Invoke-RestMethod -Method Post -Uri "$base/corpora/$($corpus.id)/workflow-runs"
$run | Select-Object id,status,current_stage,analysis_run_id,examination_run_id,review_session_id
```

**Expected:** status `waiting_for_review`, stage `wait_for_review`, and linked analysis,
examination, and review IDs. **Proves:** visible Understand → Examine → review-gate orchestration;
the agent stops for a human.

## F. Inspect Understand facts and provenance

**Action**

```powershell
$understanding = Invoke-RestMethod "$base/corpora/$($corpus.id)/analysis-runs/$($run.analysis_run_id)/understanding"
$understanding.facts | Select-Object category,subject_key,normalized_value,support_status,citation
$understanding.contradictions | Select-Object contradiction_type,reason,fact_a,fact_b
$understanding.stage_events | Select-Object stage_name,status,skip_reason,model_operation_count
```

**Expected:** supported facts contain exact quote, immutable source version/SHA, native locator,
and span; unsupported inspection fields are explicit; contradictions retain both fact sides;
canonical stages are visible. **Proves:** grounded Understand, no bluffing, and path visibility.

## G. Inspect Examine findings

**Action**

```powershell
$findings = Invoke-RestMethod "$base/corpora/$($corpus.id)/examination-runs/$($run.examination_run_id)/findings"
$findings | Select-Object rule_id,outcome,severity,message,evidence_kind,fact_ids,contradiction_ids,citations
```

**Expected:** rules have PASS/FAIL/WARNING/UNKNOWN outcomes; definitive findings carry grounded
references; UNKNOWN has no fabricated citations. **Proves:** versioned rule evaluation and honest
evidence semantics.

## H. Human review: approve, reject, and reviewer edit

**Action:** open <http://localhost:5173>. In **Human review**, enter `$corpus.id` and
`$run.examination_run_id`, then choose three different required findings:

1. **Approve** one item after inspecting its evidence.
2. **Reject** one item.
3. Enter a **Reviewer-authored edit**, check the explicit “not system-grounded” acknowledgement,
   and submit it.
4. Decide every remaining required item. Optional PASS items may remain pending.

**Expected:** each item shows a terminal decision state; edits are labeled
`REVIEWER-AUTHORED` and `NOT SYSTEM-GROUNDED`; grounded originals and citations remain visible.
**Proves:** real mixed item-level decisions, explicit edit acknowledgement, and evidence-preserving
human review.

## I. Complete review

**Action:** in the same panel, select **Complete review session**.

**Expected:** completion is disabled until all required items are decided; afterward the session is
shown as completed and immutable and all decision controls are disabled. **Proves:** review cannot
be bypassed or mutated after completion.

## J. Resume workflow

**Action:** in **Workflow status**, enter `$corpus.id` and `$run.id`, load the run, then select
**Resume workflow**.

**Expected:** Resume is available only after review completion. The run becomes `completed`;
no decision is created by resume. **Proves:** truthful durable resume after the explicit gate.

## K. Inspect usage and cost

**Action:** inspect **Stage timing and cost** in the loaded workflow, or run:

```powershell
Invoke-RestMethod "$base/corpora/$($corpus.id)/workflow-runs/$($run.id)/usage" | ConvertTo-Json -Depth 8
```

**Expected:** outer duration, nested stage records, model operation/attempt counts, pricing basis,
and deterministic `estimated_cost_usd=0` / `zero_deterministic`. **Proves:** honest Behavior 10
measurement without fabricated live-provider pricing.

## L. Explicit publication

**Action:** first confirm no register exists:

```powershell
curl.exe -sS -o NUL -w "%{http_code}`n" "$base/corpora/$($corpus.id)/register"
```

Then in **Published register**, enter `$corpus.id` and `$run.review_session_id`, load the state, and
select **Publish register**.

**Expected:** the pre-publication request is 404; Publish is offered only for a completed review;
the published register is displayed. **Proves:** workflow completion is not publication and
publication is explicit.

## M. Inspect the final register

**Action:** inspect the register UI and save the API response:

```powershell
$register = Invoke-RestMethod "$base/corpora/$($corpus.id)/register"
$register | ConvertTo-Json -Depth 10
```

**Expected:** immutable version identity, publication metadata, applied item count, review source,
grounded facts, exact quotes, native locators, SHA provenance, and publication events.
**Proves:** the Project Assurance Register is the authoritative reviewed output.

## N. Verify rejected omission

**Action**

```powershell
$register.omitted_rejected_rule_ids
$register.items.rule_id
```

**Expected:** the rejected rule is listed as omitted and is absent from applied item rule IDs.
**Proves:** rejection removes only that item and does not discard approved siblings.

## O. Verify reviewer-authored distinction

**Action:** inspect the edited register card, then run:

```powershell
$register.items | Where-Object reviewer_authored | Select-Object rule_id,content_origin,system_grounded,reviewer_authored,reviewer_authored_acknowledged,reviewer_authored_content
```

**Expected:** `content_origin=mixed`, `system_grounded=false`, `reviewer_authored=true`, and
acknowledgement is true; the original evidence remains in its separate block. **Proves:** reviewer
text is never represented as system-grounded.

## P. Verify production-readiness contradiction and citations

**Action**

```powershell
$production = $register.items | Where-Object rule_id -eq "spa.milestone.production-readiness"
$production.contradictions | ConvertTo-Json -Depth 8
$production.citations | Select-Object source_logical_name,native_locator,exact_quote,source_version_id,source_sha256
```

**Expected:** both `2026-10-30` and `2026-11-14` remain visible with `Project Charter` and
`Weekly Status Report` provenance. **Proves:** contradictory sources are surfaced, not silently
reconciled.

## Q. Harbor second-corpus proof

**Action**

```powershell
uv run --directory backend python scripts/final_runtime_acceptance.py http://localhost:8000
```

**Expected:** asserted Aurora and Harbor publications pass; Harbor reports
`insufficient_evidence` where appropriate. **Proves:** a second different corpus works without
corpus-name branching.

## R. Cross-corpus isolation

**Action:** inspect the same script result from Q.

**Expected:** `cross_corpus_denied=true`; the script fails if Aurora publication/evidence can be
read through Harbor scope. **Proves:** corpus isolation across final user-facing paths.

For adversarial and recovery steps S–X, initialize the disposable test database once:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance"
$env:TEST_DATABASE_URL = "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance_test"
$env:ALLOW_DESTRUCTIVE_TEST_DATABASE = "true"
uv run --directory backend python scripts/ensure_test_database.py
```

## S. Incremental one-source update

**Action**

```powershell
uv run --directory backend pytest tests/test_incremental_integration.py tests/test_adversarial_incremental.py -v --tb=short
```

**Expected:** PASS with changed-source execution, unaffected artifact reuse, canonical before/after
hash equality, and executed-versus-skipped operation evidence. **Proves:** focused incremental work,
not a disguised full-corpus rerun.

## T. Watcher recovery

**Action**

```powershell
uv run --directory backend pytest tests/test_watcher.py -v --tb=short
```

**Expected:** PASS for stable polling, same-byte deduplication, retryable recovery, terminal malformed
input, missing files, and restart-persisted watcher state. **Proves:** bounded stay-alive ingestion
and recovery.

## U. MCP stdio workflow

**Action**

```powershell
docker compose exec backend python -m app.mcp_probe
uv run --directory backend pytest tests/test_mcp_e2e.py -v --tb=short
```

**Expected:** probe reports exactly 20 expected business tools; E2E performs start → inspect →
explicit decisions → complete → resume → explicit publish → inspect register for both corpora, with
controlled hostile-input errors. **Proves:** typed machine-driven flow exposes, but does not bypass,
review or publication.

## V. Kill/resume durability

**Action**

```powershell
uv run --directory backend pytest tests/test_process_kill_resume.py -v --tb=short
```

**Expected:** a real worker subprocess is killed after a durable barrier; a new process resumes the
same run/thread without repeating completed logical work and returns to the review gate.
**Proves:** PostgreSQL checkpoint recovery after process death.

## W. Prompt-injection and no-bluffing proof

**Action**

```powershell
uv run --directory backend pytest tests/test_adversarial_injection.py tests/test_adversarial_no_bluffing.py tests/test_adversarial_mcp.py -v --tb=short
```

**Expected:** hostile source text cannot add rules, call tools, approve, publish, expose sentinels,
or turn unsupported claims into supported facts. **Proves:** documents remain untrusted data.

## X. Empty and insufficient-evidence proof

**Action**

```powershell
uv run --directory backend pytest tests/test_adversarial_no_bluffing.py tests/test_publication_api.py::test_empty_corpus_publication_is_honest_no_findings -v --tb=short
```

**Expected:** empty corpus publication is `no_findings` with zero items; missing evidence remains
UNKNOWN/insufficient rather than PASS. **Proves:** honest empty and unsupported outcomes.

## Y. Restart persistence

**Action**

```powershell
docker compose restart backend
Start-Sleep -Seconds 8
Invoke-RestMethod http://localhost:8000/ready
Invoke-RestMethod "$base/corpora/$($corpus.id)/register"
```

**Expected:** readiness returns after restart and the publication from M still resolves with the
same ID and version identity. **Proves:** final state is PostgreSQL/file-store durable, not
process-local.

## Z. Cleanup

**Action**

```powershell
docker compose down
```

**Expected:** project containers and network stop; named volumes remain. **Proves:** safe,
non-destructive local cleanup. Use `docker compose down --volumes` only when intentionally deleting
all local demonstration state.
