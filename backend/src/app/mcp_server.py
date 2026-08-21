"""Stdio MCP server over the existing application-service layer.

This process role does not reimplement ingestion, Understand, Examine, review,
durable resume, or incremental updates. Tools delegate to the same services as HTTP.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from pydantic import Field

from app.checkpointer import configure_windows_psycopg_loop
from app.config import Settings, get_settings
from app.errors import ConflictError, NotFoundError
from app.incremental_service import json_object, json_object_list
from app.mcp_errors import execute_mcp_tool, install_mcp_error_boundary
from app.mcp_schemas import (
    CorpusListResult,
    ExaminationInspectResult,
    IncrementalEvidenceInspectResult,
    ReviewItemListResult,
    ReviewOpenResult,
    SourceListResult,
    WorkflowStatusResult,
)
from app.review_service import session_response
from app.runtime import ApplicationServices, build_application_services
from app.schemas import (
    CorpusResponse,
    CorpusRevisionResponse,
    IncrementalEvidenceResponse,
    IncrementalRunResponse,
    ReviewDecisionCreate,
    ReviewDecisionResult,
    ReviewSessionResponse,
    SourceSummaryResponse,
    UnderstandingResponse,
    WorkflowRunEventResponse,
    WorkflowRunResponse,
)

configure_windows_psycopg_loop()

MCP_INSTRUCTIONS = (
    "Local-development trusted-client MCP interface for the Project Assurance Register. "
    "Every mutation uses the same application services as HTTP. Explicit review decisions "
    "are required; tools never auto-approve, batch-approve, or complete a session with "
    "pending required items. Production authentication is not implemented."
)
BUSINESS_TOOL_NAMES = (
    "list_corpora",
    "get_corpus",
    "list_sources",
    "start_workflow",
    "get_workflow_status",
    "resume_workflow",
    "get_understanding",
    "get_examination",
    "open_review",
    "list_review_items",
    "approve_review_item",
    "reject_review_item",
    "edit_review_item",
    "complete_review",
    "get_current_revision",
    "start_incremental_run",
    "get_incremental_evidence",
)
Comment = Annotated[str | None, Field(default=None, max_length=2_000)]


def _runtime(ctx: Context[ApplicationServices]) -> ApplicationServices:
    return ctx.request_context.lifespan_context


async def _optional_current_revision(
    runtime: ApplicationServices, corpus_id: UUID
) -> CorpusRevisionResponse | None:
    try:
        revision = await runtime.incremental.get_current_revision(corpus_id)
    except NotFoundError as error:
        if error.code != "corpus_revision_not_found":
            raise
        return None
    return CorpusRevisionResponse.model_validate(revision)


def _evidence_result(
    payload: dict[str, object],
    current_revision: CorpusRevisionResponse | None,
) -> IncrementalEvidenceInspectResult:
    base = IncrementalEvidenceResponse(
        run_id=UUID(str(payload["run_id"])),
        status=str(payload["status"]),
        change_kind=str(payload["change_kind"]),
        evidence=json_object(payload["evidence"]),
        measurement=json_object(payload["measurement"]),
        artifacts=json_object_list(payload["artifacts"]),
    )
    return IncrementalEvidenceInspectResult(
        **base.model_dump(),
        current_revision=current_revision,
    )


def create_mcp_server(
    services: ApplicationServices | None = None,
    *,
    settings: Settings | None = None,
) -> MCPServer[ApplicationServices]:
    owns_runtime = services is None

    @asynccontextmanager
    async def lifespan(
        _server: MCPServer[ApplicationServices],
    ) -> AsyncIterator[ApplicationServices]:
        runtime = services or build_application_services(
            settings or get_settings(),
            include_watcher=False,
        )
        try:
            yield runtime
        finally:
            if owns_runtime:
                await runtime.aclose()

    app_settings = settings or (services.settings if services is not None else get_settings())
    server: MCPServer[ApplicationServices] = MCPServer(
        "project-assurance-register",
        title="Project Assurance Register",
        instructions=MCP_INSTRUCTIONS,
        version=app_settings.app_version,
        lifespan=lifespan,
    )
    register_tools(server)
    install_mcp_error_boundary(server)
    return server


def register_tools(server: MCPServer[ApplicationServices]) -> None:
    @server.tool()
    async def list_corpora(
        ctx: Context[ApplicationServices],
        name: Annotated[str | None, Field(default=None, max_length=200)] = None,
    ) -> CorpusListResult:
        """List corpora, optionally filtered by exact name. No corpus-name special casing."""

        async def run() -> CorpusListResult:
            runtime = _runtime(ctx)
            corpora = await runtime.phase02.list_corpora(name=name)
            return CorpusListResult(
                corpora=[CorpusResponse.model_validate(item) for item in corpora]
            )

        return await execute_mcp_tool("list_corpora", run)

    @server.tool()
    async def get_corpus(
        corpus_id: UUID,
        ctx: Context[ApplicationServices],
    ) -> CorpusResponse:
        """Inspect one corpus by identifier."""

        async def run() -> CorpusResponse:
            runtime = _runtime(ctx)
            corpus = await runtime.phase02.get_corpus(corpus_id)
            return CorpusResponse.model_validate(corpus)

        return await execute_mcp_tool("get_corpus", run)

    @server.tool()
    async def list_sources(
        corpus_id: UUID,
        ctx: Context[ApplicationServices],
    ) -> SourceListResult:
        """List logical sources in a corpus."""

        async def run() -> SourceListResult:
            runtime = _runtime(ctx)
            sources = await runtime.phase02.list_sources(corpus_id)
            return SourceListResult(
                sources=[SourceSummaryResponse.model_validate(item) for item in sources]
            )

        return await execute_mcp_tool("list_sources", run)

    @server.tool()
    async def start_workflow(
        corpus_id: UUID,
        ctx: Context[ApplicationServices],
    ) -> WorkflowRunResponse:
        """Start the durable Understand → Examine → human-review workflow for a corpus."""

        async def run() -> WorkflowRunResponse:
            runtime = _runtime(ctx)
            workflow = await runtime.workflow.create_run(corpus_id)
            return WorkflowRunResponse.model_validate(workflow)

        return await execute_mcp_tool("start_workflow", run)

    @server.tool()
    async def get_workflow_status(
        corpus_id: UUID,
        workflow_run_id: UUID,
        ctx: Context[ApplicationServices],
    ) -> WorkflowStatusResult:
        """Inspect durable workflow status, recent events, review, and current revision."""

        async def run() -> WorkflowStatusResult:
            runtime = _runtime(ctx)
            workflow = await runtime.workflow.get_run(corpus_id, workflow_run_id)
            events = await runtime.workflow.list_events(corpus_id, workflow_run_id)
            review = None
            if workflow.review_session_id is not None:
                session = await runtime.review.get_session(corpus_id, workflow.review_session_id)
                review = session_response(session)
            current_revision = await _optional_current_revision(runtime, corpus_id)
            return WorkflowStatusResult(
                run=WorkflowRunResponse.model_validate(workflow),
                events=[WorkflowRunEventResponse.model_validate(event) for event in events],
                review=review,
                current_revision=current_revision,
            )

        return await execute_mcp_tool("get_workflow_status", run)

    @server.tool()
    async def resume_workflow(
        corpus_id: UUID,
        workflow_run_id: UUID,
        ctx: Context[ApplicationServices],
    ) -> WorkflowRunResponse:
        """Resume a durable workflow. Does not create review decisions or auto-approve."""

        async def run() -> WorkflowRunResponse:
            runtime = _runtime(ctx)
            workflow = await runtime.workflow.resume_run(corpus_id, workflow_run_id)
            return WorkflowRunResponse.model_validate(workflow)

        return await execute_mcp_tool("resume_workflow", run)

    @server.tool()
    async def get_understanding(
        corpus_id: UUID,
        analysis_run_id: UUID,
        ctx: Context[ApplicationServices],
    ) -> UnderstandingResponse:
        """Inspect grounded Understand facts, contradictions, and stage events."""

        async def run() -> UnderstandingResponse:
            runtime = _runtime(ctx)
            return await runtime.understand.get_understanding(corpus_id, analysis_run_id)

        return await execute_mcp_tool("get_understanding", run)

    @server.tool()
    async def get_examination(
        corpus_id: UUID,
        examination_run_id: UUID,
        ctx: Context[ApplicationServices],
    ) -> ExaminationInspectResult:
        """Inspect Examine summary and findings with grounded evidence references."""

        async def run() -> ExaminationInspectResult:
            runtime = _runtime(ctx)
            summary = await runtime.examine.get_summary(corpus_id, examination_run_id)
            findings = await runtime.examine.list_finding_responses(corpus_id, examination_run_id)
            return ExaminationInspectResult(summary=summary, findings=findings)

        return await execute_mcp_tool("get_examination", run)

    @server.tool()
    async def open_review(
        corpus_id: UUID,
        examination_run_id: UUID,
        ctx: Context[ApplicationServices],
    ) -> ReviewOpenResult:
        """Create or reuse the explicit human-review session for an examination run."""

        async def run() -> ReviewOpenResult:
            runtime = _runtime(ctx)
            session, created = await runtime.review.create_session(corpus_id, examination_run_id)
            return ReviewOpenResult(session=session_response(session), created=created)

        return await execute_mcp_tool("open_review", run)

    @server.tool()
    async def list_review_items(
        corpus_id: UUID,
        review_session_id: UUID,
        ctx: Context[ApplicationServices],
    ) -> ReviewItemListResult:
        """List review items with finding metadata, citations, quotes, and review state."""

        async def run() -> ReviewItemListResult:
            runtime = _runtime(ctx)
            items = await runtime.review.list_items(corpus_id, review_session_id)
            return ReviewItemListResult(items=items)

        return await execute_mcp_tool("list_review_items", run)

    @server.tool()
    async def approve_review_item(
        corpus_id: UUID,
        review_session_id: UUID,
        item_id: UUID,
        ctx: Context[ApplicationServices],
        comment: Comment = None,
    ) -> ReviewDecisionResult:
        """Explicitly approve one review item through the Phase 05 review service."""

        async def run() -> ReviewDecisionResult:
            runtime = _runtime(ctx)
            return await runtime.review.record_decision(
                corpus_id,
                review_session_id,
                item_id,
                ReviewDecisionCreate(
                    action="approve",
                    comment=comment,
                    actor="mcp",
                    decision_source="api",
                ),
            )

        return await execute_mcp_tool("approve_review_item", run)

    @server.tool()
    async def reject_review_item(
        corpus_id: UUID,
        review_session_id: UUID,
        item_id: UUID,
        ctx: Context[ApplicationServices],
        comment: Comment = None,
    ) -> ReviewDecisionResult:
        """Explicitly reject one review item through the Phase 05 review service."""

        async def run() -> ReviewDecisionResult:
            runtime = _runtime(ctx)
            return await runtime.review.record_decision(
                corpus_id,
                review_session_id,
                item_id,
                ReviewDecisionCreate(
                    action="reject",
                    comment=comment,
                    actor="mcp",
                    decision_source="api",
                ),
            )

        return await execute_mcp_tool("reject_review_item", run)

    @server.tool()
    async def edit_review_item(
        corpus_id: UUID,
        review_session_id: UUID,
        item_id: UUID,
        edited_content: Annotated[str, Field(min_length=1, max_length=8_000)],
        reviewer_authored_acknowledged: bool,
        ctx: Context[ApplicationServices],
        comment: Comment = None,
    ) -> ReviewDecisionResult:
        """Edit one item. Requires edited_content and reviewer_authored_acknowledged=true."""

        async def run() -> ReviewDecisionResult:
            runtime = _runtime(ctx)
            return await runtime.review.record_decision(
                corpus_id,
                review_session_id,
                item_id,
                ReviewDecisionCreate(
                    action="edit",
                    edited_content=edited_content,
                    reviewer_authored_acknowledged=reviewer_authored_acknowledged,
                    comment=comment,
                    actor="mcp",
                    decision_source="api",
                ),
            )

        return await execute_mcp_tool("edit_review_item", run)

    @server.tool()
    async def complete_review(
        corpus_id: UUID,
        review_session_id: UUID,
        ctx: Context[ApplicationServices],
    ) -> ReviewSessionResponse:
        """Complete review only when every required item has an explicit terminal decision."""

        async def run() -> ReviewSessionResponse:
            runtime = _runtime(ctx)
            session = await runtime.review.complete_session(corpus_id, review_session_id)
            return session_response(session)

        return await execute_mcp_tool("complete_review", run)

    @server.tool()
    async def get_current_revision(
        corpus_id: UUID,
        ctx: Context[ApplicationServices],
    ) -> CorpusRevisionResponse:
        """Inspect the current corpus revision / incremental baseline."""

        async def run() -> CorpusRevisionResponse:
            runtime = _runtime(ctx)
            revision = await runtime.incremental.get_current_revision(corpus_id)
            return CorpusRevisionResponse.model_validate(revision)

        return await execute_mcp_tool("get_current_revision", run)

    @server.tool()
    async def start_incremental_run(
        corpus_id: UUID,
        ctx: Context[ApplicationServices],
        baseline_revision_id: UUID | None = None,
    ) -> IncrementalRunResponse:
        """Start a focused incremental run. A stale baseline remains stale."""

        async def run() -> IncrementalRunResponse:
            runtime = _runtime(ctx)
            incremental = await runtime.incremental.create_run(
                corpus_id,
                baseline_revision_id=baseline_revision_id,
            )
            if incremental.status == "stale_baseline":
                raise ConflictError(
                    "stale_baseline",
                    incremental.error_detail
                    or "The supplied baseline is not the current corpus revision.",
                    incremental.error_action or "Reload the current corpus revision and retry.",
                )
            return IncrementalRunResponse.model_validate(incremental)

        return await execute_mcp_tool("start_incremental_run", run)

    @server.tool()
    async def get_incremental_evidence(
        corpus_id: UUID,
        incremental_run_id: UUID,
        ctx: Context[ApplicationServices],
    ) -> IncrementalEvidenceInspectResult:
        """Inspect incremental executed-versus-reused evidence and the current corpus revision."""

        async def run() -> IncrementalEvidenceInspectResult:
            runtime = _runtime(ctx)
            payload = await runtime.incremental.get_evidence(corpus_id, incremental_run_id)
            current_revision = await _optional_current_revision(runtime, corpus_id)
            return _evidence_result(payload, current_revision)

        return await execute_mcp_tool("get_incremental_evidence", run)


mcp = create_mcp_server()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
