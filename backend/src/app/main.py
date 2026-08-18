from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.db import (
    ReadinessProbe,
    ReadinessReport,
    check_dependencies,
    create_engine,
    create_session_factory,
)


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
) -> FastAPI:
    app_settings = settings or get_settings()
    engine = create_engine(app_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.engine = engine
        application.state.session_factory = create_session_factory(engine)
        application.state.readiness_probe = readiness_probe or partial(
            check_dependencies,
            engine,
            app_settings.readiness_timeout_seconds,
        )
        yield
        await engine.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        description="Development foundation only; Task 1 business workflow is not implemented.",
        lifespan=lifespan,
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

    return application


app = create_app()
