# Proposed Architecture — Project Assurance Register

## Status

**Phase 01 foundation and Phase 02 deterministic ingestion/provenance layer are implemented.**

The executable system now includes corpus-scoped application-immutable source metadata, mounted source-file
storage, streamed hashing, PDF/DOCX/Markdown/TXT parsers, normalized source blocks, exact citation
resolution, and deterministic pgvector retrieval. Register records, agent graphs, model calls,
human review, MCP business tools, durable workflow resume, incremental updates, and the watcher
remain planned. Implementation evidence may simplify or revise those plans; revisions are recorded
in `PROGRESS.md`.

## Design goals

The architecture exists to prove:

- the understand, examine, and stay-alive movements;
- visible stages with real retry, skip, and human-escalation branches;
- durable resume after process death;
- a real item-level human gate;
- complete machine operation with explicit gate operations;
- exact source provenance and no bluffing;
- focused incremental updates and exact unchanged-content proof;
- idempotency, concurrent-run isolation, and safe publication; and
- keyless executable evidence.

It does not exist to demonstrate infrastructure breadth.

The explicit non-cuttable floor is limited to behaviors 1–5: visible path-changing stages, durable resume, item-level human review, machine-driven flow, and no-bluffing. Understand, examine, and stay alive must each remain genuinely represented, but detailed sub-features inside the movements may be cut with explicit rationale.

One-command stranger setup, real keyless tests, document prompt-injection defense, concurrent isolation, and stage timing/cost are behaviors 6–10. Each is a **Strong differentiator — may be cut only with explicit rationale if time forces a trade-off.** They remain planned and prioritized architecture targets, not absolute minimum acceptance gates.

## Stack classification

Assignment requested/preferred:

- Python with FastAPI;
- an orchestration framework such as LangGraph or LangChain;
- PostgreSQL with vector search; and
- React.

The assignment allows comparable orchestration/tools when justified.

Our chosen implementation is Python, FastAPI, LangGraph, PostgreSQL with pgvector, React with TypeScript, and MCP. MCP is the strongest chosen machine-interface shape, not an absolute assignment mandate.

## Implemented Phase 01/02 runtime

The current runtime boundary is deliberately small:

```mermaid
flowchart LR
    Browser[ReactStatusShell] -->|/api/*| Nginx[Nginx]
    Nginx --> API[FastAPI]
    API --> Services[Phase02Services]
    Services --> DB[(PostgreSQL17_pgvector)]
    Services --> Store[MountedSourceStore]
    Alembic[AlembicStartupMigration] --> DB
```

- Nginx serves immutable Vite production assets and proxies `/api/*` to FastAPI.
- FastAPI owns liveness/readiness/version plus corpus, source, citation, and retrieval routes.
- `/health` has no database dependency.
- `/ready` performs a bounded PostgreSQL connection check and verifies `pg_extension` contains
  `vector`; safe structured HTTP 503 output is returned otherwise.
- SQLAlchemy creates an async engine/session factory during application lifespan and provides
  corpus-scoped Phase 02 services.
- Alembic revision `20260819_0001` enables `vector`; revision `20260819_0002` creates `corpora`,
  `sources`, `source_versions`, and `source_blocks`, including `vector(64)` and HNSW cosine index.
- Compose orders startup by health: database, migrating backend, then frontend.
- PostgreSQL and source bytes use separate named persistent volumes. No Redis, queue, or
  additional service exists.
- Phase 02 actively uses pgvector's Python package for `vector(64)` persistence and retrieval.
  LangGraph, its PostgreSQL checkpointer, and MCP remain locked but unused.

Supported/common parser and driver failures exercised by tests expose controlled errors. Exhaustive
malformed-input containment and parser isolation are not claimed. The configured database URL is
represented as a Pydantic `SecretStr`, and no model/API key is required.

## Implemented Phase 02 data layer

### Records and constraints

- `Corpus` is the isolation and declared-format boundary.
- `Source` is unique by `(corpus_id, logical_name)`.
- `SourceVersion` is unique by `(source_id, sha256)`, has a globally unique generated storage key,
  and redundantly carries `corpus_id` under a composite source/corpus foreign key.
- `SourceBlock` is unique by version/block index and version/native locator and carries a composite
  version/corpus foreign key.
- Version and block mutation endpoints do not exist. Changed bytes create another version; exact
  duplicate bytes for one logical source return the existing version.
- `SourceVersion` and `SourceBlock` are immutable by application contract and API/service behavior.
  Database UPDATE/DELETE prevention triggers and restricted mutation roles are not implemented.
- No Fact, Contradiction, Finding, Rule, ChangeSet, ReviewDecision, RegisterVersion, run, or
  checkpoint business table was created.

### Ingestion/storage transaction

```mermaid
flowchart LR
    Upload[UploadFile] --> Stage[UUIDStagingFile]
    Stage -->|1MiB chunks| Hash[SHA256AndSizeBound]
    Hash --> Validate[ExtensionMediaSignatureResourceChecks]
    Validate --> Parse[DeterministicParser]
    Parse --> Dedup[CorpusAndLogicalSourceDedup]
    Dedup -->|duplicate| Existing[VerifyStoredHashAndReturnVersion]
    Dedup -->|new bytes| Promote[AtomicGeneratedKeyPromotion]
    Promote --> Tx[VersionAndBlocksTransaction]
```

The default maximum upload is 10 MiB. A request-level Content-Length guard allows 1 MiB for
multipart overhead before normal multipart processing, while the streamed file-content bound
remains authoritative. Missing/chunked Content-Length cannot be rejected by the first guard and
relies on streaming enforcement.

Keys use only UUIDs, SHA-256, and a server-selected extension:
`corpus/source/hash-prefix/hash/version.ext`. Client filenames are metadata only and filenames with
path separators, drive separators, or traversal components are rejected. In-process failures
attempt staged/promoted-file cleanup.

A crash after promotion but before database commit can leave an orphan. Cancellation edges require
later reconciliation, and cleanup failures are best-effort. Transactional outbox/object-store
reconciliation remains deferred with durable workflow recovery.

DOCX ZIP validation bounds entry count (1,000), each expanded entry (20 MiB), total expanded size
(50 MiB), and compression ratio (200:1). PDF parsing is text-only; no extractable blocks produces a
typed `textless_pdf` failure and no OCR fallback.

### Parser locator/normalization contract

- PDF: `page[n]/block[n]`, where page number is one-based and parser block index is zero-based.
- DOCX: `paragraph[n]` or
  `table[n]/row[n]/cell[n]/paragraph[n]`, all deterministic document-order indexes.
- Markdown/TXT: `lines[start-end]/block[n]`, with one-based inclusive source line ranges.

Normalized block text uses LF line endings, Unicode NFC, regular spaces for NBSP, removed trailing
whitespace on each line, and removed blank boundary lines. Interior line structure is retained.
`normalized_start` is zero for a stored block and `normalized_end` is its PostgreSQL/Python
character length. Citation spans are half-open offsets within that block.

### Exact citation resolution

Resolution order is source-version lookup scoped by corpus, source-file SHA-256 recalculation,
citation SHA/format comparison, deterministic fresh parsing of the original bytes, native-locator
lookup in that fresh parse, persisted-block integrity comparison, fresh span bounds check, and exact
quote comparison. Source bytes are re-hashed after parsing to reduce the hash/parse race window.
Missing/cross-corpus versions are not found. Persisted block text or a vector result cannot bypass
this resolver.

### Deterministic pgvector retrieval

Source text tokens are case-folded and SHA-256 feature-hashed into 64 signed dimensions, then
L2-normalized. PostgreSQL stores the vector and performs cosine-distance ordering under corpus plus
optional format/block-type filters. Zero-token queries are rejected. This is deterministic lexical
retrieval support for local tests, not a model gateway or semantic embedding claim.

## Planned system shape

Use one modular application codebase with a small number of process roles:

```mermaid
flowchart LR
    Human[HumanReviewer] --> UI[ReactReviewUI]
    UI --> API[FastAPI]
    Machine[MCPClient] --> MCP[MCPServer]
    MCP --> App[ApplicationServices]
    API --> App
    Watcher[SimpleInboxWatcher] --> App
    Worker[LangGraphWorker] --> App
    App --> DB[(PostgreSQL_pgvector)]
    App --> Store[HashAddressedFileStore]
    App --> Model[ModelGateway]
```

The API, worker, watcher, and MCP server are process roles from the same codebase and share application services and storage rules. They are not independent microservices.

Hosted deployment is not explicitly required by Task 1. Our minimum acceptance target is a reproducible local/container deployment. Hosted deployment will be attempted only after all mandatory Task 1 behaviors and evidence are green.

## Component responsibilities

### FastAPI

Implemented now:

- stream bounded uploads to durable file storage;
- create/inspect corpora, logical sources, immutable versions, and blocks;
- validate exact citations and run corpus-scoped deterministic retrieval.

Later planned responsibilities:

- create rules and runs;
- expose run status and visible stage events;
- expose pending review items and explicit item-level decision operations;
- resume workflows after accepted human decisions;
- serve immutable source snippets/locators safely; and
- return truthful failure states with cause and remedy.

### LangGraph worker

Planned responsibilities:

- execute visible stateful stages;
- use persisted checkpoints;
- make conditional retry/skip/escalation decisions;
- interrupt at `WAITING_FOR_REVIEW`;
- resume only after valid explicit decisions exist; and
- record stage outcomes and usage before advancing.

### PostgreSQL with pgvector

Implemented now: corpus/source/version/block metadata, composite corpus constraints, deterministic
vectors, HNSW indexing, and metadata-filtered retrieval.

Later planned responsibilities:

- durable run state and LangGraph checkpoints;
- run/job claiming and attempt records;
- idempotency keys and operation results;
- extracted facts, contradictions, rules, findings, and citations;
- proposed change sets and human decisions;
- published register versions and item hashes; and
- append-only stage, usage, and change-attribution events.

pgvector assists retrieval recall. It is not evidence and cannot satisfy provenance.

### Hash-addressed file store

The implemented local/container adapter streams originals outside process memory, incorporates
SHA-256 into generated version keys, uses a mounted named volume, and re-reads/reparses bytes for
citation validation. Normalized blocks are stored in PostgreSQL rather than as duplicate filesystem
artifacts. Object storage is not required for the acceptance target.

### React review UI

Only essential review behavior is planned:

- run and stage timeline;
- proposed register changes, contradictions, and findings;
- exact source evidence view;
- individual approve/reject controls in one review;
- explicit submit action by a real human; and
- status/resume and published-result view.

Rich editing, visual polish, and elaborate observability dashboards are optional cuts.

### Chosen MCP server

Planned as a thin adapter over the same application services as FastAPI:

- create/upload/configure a corpus and run;
- inspect status and stage decisions;
- retrieve pending item-level review proposals;
- submit explicit approve/reject decisions;
- resume the interrupted graph; and
- verify the resulting published register and audit history.

MCP exposes the gate but does not bypass it. The demonstrated path must not let the proposing agent automatically approve its own proposals. This is a workflow requirement, not an added RBAC or proposer/reviewer identity-separation requirement.

### Simple watched inbox

The minimum watcher polls a mounted directory, waits for file size/mtime stability, hashes content, and creates an idempotent source-arrival operation. A sophisticated event system is unnecessary unless executable evidence shows polling cannot satisfy focused incremental behavior.

## Core records

Implemented in Phase 02:

- `Corpus`: isolation boundary and declared domain/format policy.
- `Source`: logical document identity.
- `SourceVersion`: immutable content hash, storage key, parser status, and arrival time.
- `SourceBlock`: format-native locator, normalized text/span, metadata, and required deterministic
  embedding.

Planned for later phases:

- `Run`: corpus, trigger, state, checkpoint/thread identity, and status.
- `StageEvent`: decision, attempt, outcome, timing, usage, and error/remedy.
- `Fact`: typed extracted assertion with source citations and support status.
- `Contradiction`: incompatible assertions with every side cited.
- `RuleSet` and `Rule`: user-supplied versioned examination configuration.
- `Finding`: rule result, severity/rationale, and source/register locations.
- `RegisterItem`: stable assurance item with canonical serialized content.
- `ChangeSet` and `ChangeItem`: immutable proposals and their before/after hashes.
- `ReviewDecision`: human actor, item, approve/reject decision, optional reason, and timestamp.
- `RegisterVersion`: published version and ordered item hashes.
- `IdempotencyRecord`: operation key, durable status, and prior result.

Every query and uniqueness rule must include the appropriate corpus, source, run, or register-version identity. Do not rely on process-local global state.

## Planned agent graph

```mermaid
flowchart TD
    StartNode[RunCreated] --> Ingest[IngestAndHash]
    Ingest --> Classify[ClassifyDocument]
    Classify -->|"supported"| Parse[ParseAndIndex]
    Classify -->|"unsupported"| Skip[SafeSkipWithReason]
    Parse --> Plan[PlanAffectedWork]
    Plan --> Extract[RetrieveAndExtract]
    Extract --> Validate[ValidateSchemaAndGrounding]
    Validate -->|"retryable"| Retry[BoundedRetry]
    Retry --> Extract
    Validate -->|"unsafe_or_exhausted"| Escalate[EscalateForHumanReview]
    Validate -->|"valid"| Conflict[DetectContradictions]
    Conflict --> Draft[DraftRegisterChanges]
    Draft --> Examine[ExamineRulesInStages]
    Examine --> ReviewSet[BuildImmutableReviewSet]
    Skip --> ReviewSet
    Escalate --> ReviewSet
    ReviewSet --> Waiting[WAITING_FOR_REVIEW]
    Waiting --> HumanDecision[HumanSubmitsItemDecisions]
    HumanDecision --> Apply[ApplyApprovedItemsOnly]
    Apply --> Verify[VerifyPublishedState]
    Verify -->|"valid"| Complete[COMPLETED]
    Verify -->|"invalid"| Failed[FAILED_WITH_CAUSE_AND_REMEDY]
```

Visible stage events must record the selected branch and reason. Retry is bounded. Skip must state the unsupported input and remedy. Escalation creates a review item rather than silently continuing.

## Human gate state machine

The required demonstrated path is:

```text
PROPOSING
→ WAITING_FOR_REVIEW
→ real human inspects each item
→ human explicitly approves/rejects individual items
→ decisions submitted through UI/API/MCP operation
→ READY_TO_RESUME
→ APPLYING_APPROVED_ITEMS
→ VERIFYING
→ COMPLETED
```

Rules:

- A proposal set is immutable once presented.
- Review submission includes the proposal-set version to prevent stale decisions.
- Every actionable item in the presented review set requires an explicit decision before resume. Mixed approval/rejection is required; unresolved items cannot be silently treated as approved or rejected.
- One submission can contain approvals and rejections.
- Rejected items remain in audit history but do not alter the published register.
- The proposing agent has no operation that implicitly self-approves.
- React and MCP/API use the same decision validation and publication path.
- Success is returned only after approved changes are durable and the published version passes verification.

## Exact provenance

The implemented source citation is:

```text
source_version_id
source_sha256
format
native_locator
normalized_start
normalized_end
exact_quote
```

Examples of native locators:

- PDF: page plus parser block index;
- DOCX: paragraph or table/row/cell path;
- Markdown/TXT: line range plus block index.

The source version and normalized parser artifact are immutable by application contract. The
Phase 02 resolver confirms stored bytes still hash correctly, reparses them, and checks that the
fresh locator/span yields the exact quote and matches persisted block content. Later publication
code must call this same deterministic boundary; a model cannot override it.

For a finding grounded against the generated register/deliverable, the planned locator is:

```text
register_version_id
register_item_id
field_path
value_hash
exact_value
```

The register version is immutable. Before a deliverable-grounded finding is treated as supported, a deterministic validator resolves the item and field path, confirms the exact value, and verifies its hash.

## Understand movement

Planned stages:

1. classify document type and relevance;
2. plan entities/fact types to inspect from domain configuration;
3. retrieve candidate blocks using metadata/entity filters plus pgvector;
4. extract typed facts with citations;
5. validate schema and exact grounding;
6. cluster compatible assertions;
7. emit contradictions when materially incompatible assertions remain; and
8. draft stable register items or explicit unsupported gaps.

Configuration defines document types, assurance areas, fact schemas, and normalization rules. Avoid corpus-name conditionals and one-off fixture logic.

## Examine movement

Rules are versioned user data with fields such as applicability, target, condition, severity, expected evidence, and rationale.

Planned stages:

1. determine applicability;
2. evaluate source evidence;
3. evaluate proposed register state;
4. validate finding provenance;
5. deduplicate related findings; and
6. report violated, satisfied, not-applicable, or unsupported outcomes.

An honest no-findings result requires a completed applicable-rule count and zero violated findings. A skipped or failed examination must never be reported as no findings.

## Incremental stay-alive movement

For each stable new file/source version:

1. stream, hash, and deduplicate the content;
2. parse/index only the new source version;
3. extract candidate entity keys and changed facts;
4. find potentially affected register items through stable keys, citation backlinks, contradiction groups, rule dependencies, and conservative semantic retrieval;
5. record the planned affected set before generation;
6. re-run understand/examine only for that set;
7. create item-level changes with before/after hashes;
8. surface new contradictions;
9. wait for real human review;
10. apply only approved changes to a new register version; and
11. verify every unaffected item retains identical canonical bytes and SHA-256.

The audit ledger records source cause, affected item IDs, preserved item IDs, executed stage IDs, model-operation/idempotency keys, processed source versions, canonical before/after hashes, decisions, timestamp, and resulting version.

A new source may be fully parsed/indexed. Existing unaffected sources and register items must not receive a full-corpus model pass disguised as incremental work.

Incremental evidence compares all of those fields before and after the update. Hash equality proves preservation, but hash equality alone does not prove that a full rerun was avoided.

## Durability, idempotency, and concurrency

Durable resume is non-cuttable behavior 2. Concurrent-run isolation is planned behavior 9: **Strong differentiator — may be cut only with explicit rationale if time forces a trade-off.**

Start simple and PostgreSQL-backed:

- Use LangGraph’s PostgreSQL checkpointer if package/runtime verification shows it satisfies process-kill recovery.
- Store a durable job/run row with status, attempt, lease/heartbeat timestamps, and checkpoint/thread identity.
- Claim available work using a short PostgreSQL transaction, such as row locking with `FOR UPDATE SKIP LOCKED`, then perform long work outside the claim transaction.
- Use unique idempotency keys for upload content, run triggers, model-stage operations, watcher arrivals, review submissions, and publication.
- Before a costly external call, persist the operation key and attempt.
- Use provider idempotency when available.
- Persist the returned structured result before graph advancement and reuse that durable completed result on resume.
- Retry only when non-completion is known.
- If the provider outcome is unknowable, record an honest ambiguous state and reconcile/retry rather than claiming exactly-once behavior.
- Use optimistic register-version checks and a short row lock or advisory lock during publication.
- Enforce unique publication per accepted change-set version.
- Keep checkpoints and stage results scoped by run identity.

This is a proposed mechanism, not implemented SQL.

A transactional outbox is deliberately not part of the initial commitment. Introduce it only if later implementation needs atomic database-to-external-message delivery that the simple job/checkpoint design cannot prove safely.

Required behavior 2 evidence:

- kill a real worker subprocess after a durable failpoint, restart, and reuse completed stage results;

Planned behavior 9 and additional idempotency evidence:

- process two distinct runs simultaneously with no cross-run state;
- process two same-corpus runs simultaneously with safe version conflict behavior; and
- repeat operations and prove no duplicated source, cost record, review application, or publication.

## Trust boundaries and prompt-injection defense

Document prompt-injection defense is planned behavior 8: **Strong differentiator — may be cut only with explicit rationale if time forces a trade-off.**

Trust order:

1. system policy and deterministic validators;
2. explicit real-human decisions submitted through the review operation;
3. versioned user rule configuration;
4. application metadata; and
5. untrusted document text.

Document content is wrapped and labeled as quoted evidence. It cannot:

- replace system policy;
- alter graph transitions directly;
- invoke tools;
- read environment secrets;
- mark itself supported without a valid locator;
- approve a proposal; or
- suppress a contradiction/finding.

An adversarial document must be retained and cited as data while producing no unauthorized action.

This trust ordering does not require RBAC or proposer/reviewer identity separation for the assignment demonstration.

## No-bluffing and failure semantics

- Supported claims require at least one valid exact citation.
- Unsupported claims remain explicit and cannot be rendered as sourced facts.
- Contradictory evidence remains visible until a human decision; it is not silently reconciled.
- `COMPLETED` requires a durable published version, applied-decision audit, and successful provenance/hash verification.
- Examination failure is not “no findings.”
- A watcher parse failure is not “no change.”
- Errors expose safe cause/remedy information without source contents or secrets.
- Demonstrated model/dependency failure paths should use a working deterministic fallback, bounded retry, safe skip, or human escalation where that path has been implemented and tested.
- If no safe fallback exists, preserve durable state, expose cause and remedy, remain resumable, and do not falsely report success.
- No fallback path currently exists or is claimed; all are planned pending executable evidence.

## Observability and cost

Behavior 10 is planned as a **Strong differentiator — may be cut only with explicit rationale if time forces a trade-off.** Its proposed durable stage event records:

- stage and branch;
- start/end timestamps and elapsed duration;
- attempt/retry count;
- input/output token counts when available;
- model/provider name when used;
- pricing snapshot/basis when configured;
- estimated cost or honest `unavailable`;
- idempotency/cache reuse; and
- safe error class plus remedy.

An elaborate observability UI is optional. The durable data and minimal timeline/report remain prioritized Behavior 10 targets rather than part of the explicit five-behavior floor.

Measurement must state the method before results, report variance and tail values such as p95/max, and state limitations. Raw measurement data will be committed to the repository.

## Keyless test architecture

Behavior 7 is planned as a **Strong differentiator — may be cut only with explicit rationale if time forces a trade-off.**

If Behavior 7 is retained, a deterministic model adapter supplies controlled structured responses only at the model boundary while tests still use:

- real document parsers and provenance validators;
- real LangGraph transitions and interrupts;
- real PostgreSQL/pgvector in containers;
- real worker subprocess kill/restart;
- real concurrent workers/transactions;
- real FastAPI and MCP transport contracts; and
- actual canonical serialization/hash comparisons.

Fixtures must include:

- grounded agreement;
- a contradiction;
- a missing/unsupported fact;
- a clean rule set with no findings;
- a violated rule;
- a changed rule/domain configuration that changes behavior without code changes;
- document prompt injection;
- a focused later source update; and
- a second different project corpus.

## Security and data handling

- Fixtures and demonstrations use synthetic/public data only.
- Uploads use a Content-Length request guard plus a streamed file-content bound; file type and DOCX
  expansion checks cover the supported/tested cases with cause/remedy errors.
- Parsers currently run in-process without a separate timeout/sandbox; this remains a documented
  local-development limitation.
- Source filenames and parser text are never treated as commands.
- Secrets are environment-injected and redacted from logs/errors.
- Integration `TRUNCATE` is guarded by a fixed disposable database name, a distinct application
  database name, and an explicit destructive-test opt-in.
- Corpus/run IDs scope every read/write.
- Review decisions record a human actor and proposal version.
- Phase 02 source versions/blocks are not overwritten through application APIs/services; database
  mutation-prevention triggers and restricted roles are absent.
- No certification or guaranteed-redaction claim is made.

## Deliberate exclusions and cut order

Defer or cut optional breadth in this order before reducing prioritized differentiators:

1. UI polish;
2. hosted deployment;
3. CSV;
4. multiple model providers;
5. elaborate observability UI;
6. sophisticated watcher implementation; and
7. extra format breadth.

Never cut the five explicit floor behaviors: visible path-changing stages, durable resume, real item-level human review, machine-driven flow, or no-bluffing. Understand, examine, and stay alive must each remain genuinely represented; detailed sub-features inside them may be cut with explicit rationale.

Behaviors 6–10 remain prioritized. Each is a **Strong differentiator — may be cut only with explicit rationale if time forces a trade-off.**

Explicitly out of scope:

- Kubernetes, Terraform, Kafka, Redis, Celery, and microservices;
- OCR/handwriting in the initial version;
- spreadsheet output/editing;
- live multiplayer editing;
- document-management-system behavior;
- unsupported certifications or guaranteed redaction; and
- Task 2, Task 3, Task 4, and extra-credit implementation.

## Architecture validation gates

This planned architecture becomes documented implementation only as matching evidence passes. The minimum gate is the five-behavior floor plus a genuine representation of all three movements; behaviors 6–10 remain strong-differentiator targets:

1. package/version compatibility and local/container skeleton;
2. exact parser locator round-trips;
3. grounded understand and examine graphs;
4. real human `WAITING_FOR_REVIEW` flow;
5. mandatory kill/resume evidence and planned Behavior 9 concurrent-publication evidence;
6. incremental affected-set and unchanged hash evidence;
7. UI and MCP/API shared-gate behavior;
8. planned Behavior 7/8/10 adversarial, keyless, and measurement evidence; and
9. planned Behavior 6 fresh-clone local/container audit on a second corpus.

If a behavior 6–10 gate is cut, `PROGRESS.md` and README must record the explicit rationale and limitation rather than treating it as failed minimum acceptance.
