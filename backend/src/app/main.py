import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from functools import partial

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api import router as phase02_router
from app.checkpointer import configure_windows_psycopg_loop
from app.config import Settings, get_settings
from app.db import (
    ReadinessProbe,
    ReadinessReport,
    check_dependencies,
    create_engine,
)
from app.errors import ConflictError, ModelError, NotFoundError, Phase02Error, ValidationError
from app.examine_service import ExamineService
from app.incremental_service import IncrementalService
from app.model_gateway import ModelAdapter
from app.publication_service import PublicationService
from app.request_limits import UploadRequestSizeGuard
from app.review_service import ReviewService
from app.runtime import build_application_services
from app.services import Phase02Service
from app.understand_service import UnderstandService
from app.watcher import WatcherService
from app.workflow_service import WorkflowService

configure_windows_psycopg_loop()

logger = logging.getLogger("app.http")


class UnexpectedExceptionBoundary:
    """Sanitize unexpected HTTP failures before they reach ServerErrorMiddleware."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception:
            logger.error("Unhandled HTTP request failure")
            if response_started:
                await send({"type": "http.response.body", "body": b"", "more_body": False})
                return
            response = JSONResponse(
                status_code=500,
                content={
                    "code": "internal_error",
                    "detail": "The operation could not be completed safely.",
                    "action": "Retry the request or inspect service health.",
                },
            )
            await response(scope, receive, send)


class HealthResponse(BaseModel):
    status: str


class VersionResponse(BaseModel):
    app_version: str
    current_phase: str
    implementation_status: str


def create_app(
    *,
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
    phase02_service: Phase02Service | None = None,
    understand_service: UnderstandService | None = None,
    examine_service: ExamineService | None = None,
    review_service: ReviewService | None = None,
    workflow_service: WorkflowService | None = None,
    incremental_service: IncrementalService | None = None,
    publication_service: PublicationService | None = None,
    watcher_service: WatcherService | None = None,
    model_adapter: ModelAdapter | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    engine = create_engine(app_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.readiness_probe = readiness_probe or partial(
            check_dependencies,
            engine,
            app_settings.readiness_timeout_seconds,
        )
        built = build_application_services(
            app_settings,
            engine=engine,
            phase02_service=phase02_service,
            understand_service=understand_service,
            examine_service=examine_service,
            review_service=review_service,
            workflow_service=workflow_service,
            incremental_service=incremental_service,
            publication_service=publication_service,
            watcher_service=watcher_service,
            model_adapter=model_adapter,
        )
        application.state.engine = engine
        application.state.session_factory = built.session_factory
        application.state.phase02_service = built.phase02
        application.state.understand_service = built.understand
        application.state.examine_service = built.examine
        application.state.review_service = built.review
        application.state.workflow_service = built.workflow
        application.state.incremental_service = built.incremental
        application.state.publication_service = built.publication
        application.state.watcher_service = built.watcher
        stop = asyncio.Event()
        poll_task: asyncio.Task[None] | None = None
        if built.watcher is not None:
            poll_task = asyncio.create_task(built.watcher.run_forever(stop))
        yield
        stop.set()
        if poll_task is not None:
            poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await poll_task
        await engine.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        description=(
            "Phase 10 final delivery over grounded Understand, Examine, explicit human review, "
            "durable resume, focused incremental updates, MCP business operations, and "
            "approved-only register publication. MCP is a stdio adapter over the same "
            "application services as HTTP. A Railway-hosted demonstration deployment "
            "is available; it is not an SLA-backed production service."
        ),
        lifespan=lifespan,
    )
    application.add_middleware(
        UploadRequestSizeGuard,
        max_upload_bytes=app_settings.max_upload_bytes,
    )
    application.add_middleware(UnexpectedExceptionBoundary)

    @application.exception_handler(Phase02Error)
    async def phase02_error_handler(_request: Request, error: Phase02Error) -> JSONResponse:
        status_code = 422
        if isinstance(error, NotFoundError):
            status_code = 404
        elif isinstance(error, ConflictError):
            status_code = 409
        elif isinstance(error, ValidationError):
            status_code = 413 if error.code == "upload_too_large" else 400
        elif isinstance(error, ModelError):
            status_code = 503
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "detail": error.detail,
                "action": error.action,
            },
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "request_validation_error",
                "detail": "The request fields or declared format are invalid.",
                "action": (
                    "Check the OpenAPI schema and use pdf, docx, markdown, or txt "
                    "for declared_format."
                ),
            },
        )

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="alive")

    @application.get(
        "/ready",
        response_model=ReadinessReport,
        responses={503: {"model": ReadinessReport}},
    )
    async def ready(request: Request) -> ReadinessReport | JSONResponse:
        report: ReadinessReport = await request.app.state.readiness_probe()
        if report.status == "unavailable":
            return JSONResponse(status_code=503, content=report.model_dump(exclude_none=True))
        return report

    @application.get("/version", response_model=VersionResponse)
    async def version() -> VersionResponse:
        return VersionResponse(
            app_version=app_settings.app_version,
            current_phase=app_settings.current_phase,
            implementation_status=app_settings.implementation_status,
        )

    application.include_router(phase02_router)
    return application


app = create_app()
