from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api import router as phase02_router
from app.config import Settings, get_settings
from app.db import (
    ReadinessProbe,
    ReadinessReport,
    check_dependencies,
    create_engine,
    create_session_factory,
)
from app.errors import ModelError, NotFoundError, Phase02Error, ValidationError
from app.examine_service import ExamineService
from app.model_gateway import ModelAdapter, create_model_adapter
from app.request_limits import UploadRequestSizeGuard
from app.review_service import ReviewService
from app.services import Phase02Service
from app.storage import LocalFileStorage
from app.understand_service import UnderstandService


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
    model_adapter: ModelAdapter | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    engine = create_engine(app_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        session_factory = create_session_factory(engine)
        application.state.engine = engine
        application.state.session_factory = session_factory
        application.state.readiness_probe = readiness_probe or partial(
            check_dependencies,
            engine,
            app_settings.readiness_timeout_seconds,
        )
        resolved_phase02 = phase02_service or Phase02Service(
            session_factory,
            LocalFileStorage(
                app_settings.source_storage_path,
                app_settings.max_upload_bytes,
            ),
        )
        adapter = model_adapter or create_model_adapter(app_settings)
        resolved_understand = understand_service or UnderstandService(
            resolved_phase02.session_factory,
            resolved_phase02,
            adapter,
            app_settings,
        )
        application.state.phase02_service = resolved_phase02
        application.state.understand_service = resolved_understand
        resolved_examine = examine_service or ExamineService(
            resolved_phase02.session_factory,
            resolved_phase02,
            resolved_understand,
        )
        application.state.examine_service = resolved_examine
        application.state.review_service = review_service or ReviewService(
            resolved_phase02.session_factory,
            resolved_phase02,
            resolved_examine,
        )
        yield
        await engine.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        description=(
            "Phase 05 human review over grounded Examine findings. "
            "Durable resume, MCP business operations, watching, and register "
            "publication are not implemented."
        ),
        lifespan=lifespan,
    )
    application.add_middleware(
        UploadRequestSizeGuard,
        max_upload_bytes=app_settings.max_upload_bytes,
    )

    @application.exception_handler(Phase02Error)
    async def phase02_error_handler(_request: Request, error: Phase02Error) -> JSONResponse:
        status_code = 422
        if isinstance(error, NotFoundError):
            status_code = 404
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
