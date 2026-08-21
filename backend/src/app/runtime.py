"""Shared application-service construction for HTTP and MCP process roles."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings, get_settings
from app.db import SessionFactory, create_engine, create_session_factory
from app.examine_service import ExamineService
from app.incremental_service import IncrementalService
from app.model_gateway import ModelAdapter, create_model_adapter
from app.review_service import ReviewService
from app.services import Phase02Service
from app.storage import LocalFileStorage
from app.understand_service import UnderstandService
from app.watcher import WatcherService
from app.workflow_service import WorkflowService


@dataclass(slots=True)
class ApplicationServices:
    """One application-service graph shared by FastAPI and the MCP server."""

    settings: Settings
    engine: AsyncEngine
    session_factory: SessionFactory
    phase02: Phase02Service
    understand: UnderstandService
    examine: ExamineService
    review: ReviewService
    workflow: WorkflowService
    incremental: IncrementalService
    watcher: WatcherService | None
    model_adapter: ModelAdapter

    async def aclose(self) -> None:
        await self.engine.dispose()


def build_application_services(
    settings: Settings | None = None,
    *,
    engine: AsyncEngine | None = None,
    session_factory: SessionFactory | None = None,
    phase02_service: Phase02Service | None = None,
    understand_service: UnderstandService | None = None,
    examine_service: ExamineService | None = None,
    review_service: ReviewService | None = None,
    workflow_service: WorkflowService | None = None,
    incremental_service: IncrementalService | None = None,
    watcher_service: WatcherService | None = None,
    model_adapter: ModelAdapter | None = None,
    include_watcher: bool = True,
) -> ApplicationServices:
    app_settings = settings or get_settings()
    resolved_engine = engine or create_engine(app_settings)
    resolved_sessions = session_factory or create_session_factory(resolved_engine)
    resolved_phase02 = phase02_service or Phase02Service(
        resolved_sessions,
        LocalFileStorage(app_settings.source_storage_path, app_settings.max_upload_bytes),
    )
    adapter = model_adapter or create_model_adapter(app_settings)
    resolved_understand = understand_service or UnderstandService(
        resolved_phase02.session_factory,
        resolved_phase02,
        adapter,
        app_settings,
    )
    resolved_examine = examine_service or ExamineService(
        resolved_phase02.session_factory,
        resolved_phase02,
        resolved_understand,
    )
    resolved_review = review_service or ReviewService(
        resolved_phase02.session_factory,
        resolved_phase02,
        resolved_examine,
    )
    resolved_workflow = workflow_service or WorkflowService(
        resolved_phase02.session_factory,
        resolved_phase02,
        resolved_examine,
        resolved_review,
        adapter,
        app_settings,
    )
    resolved_incremental = incremental_service or IncrementalService(
        resolved_phase02.session_factory,
        resolved_phase02,
        resolved_understand,
        resolved_examine,
        resolved_review,
        adapter,
        app_settings,
    )
    resolved_watcher = watcher_service
    if include_watcher and resolved_watcher is None:
        resolved_watcher = WatcherService.from_settings(
            resolved_phase02.session_factory,
            resolved_phase02,
            resolved_incremental,
            app_settings,
        )
    elif not include_watcher:
        resolved_watcher = None
    return ApplicationServices(
        settings=app_settings,
        engine=resolved_engine,
        session_factory=resolved_phase02.session_factory,
        phase02=resolved_phase02,
        understand=resolved_understand,
        examine=resolved_examine,
        review=resolved_review,
        workflow=resolved_workflow,
        incremental=resolved_incremental,
        watcher=resolved_watcher,
        model_adapter=adapter,
    )
