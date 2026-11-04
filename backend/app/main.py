"""SpecGuard 2.0 FastAPI application entry point.

Start the server from the ``backend`` directory:

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import dashboard, impact, policies, requirements, runs, specs, tests
from app.core.config import API_VERSION, APP_VERSION, Settings, get_settings
from app.core.contracts import ErrorResponse
from app.core.errors import TRACE_HEADER, register_exception_handlers
from app.database.init_db import init_db
from app.database.seed import seed_reference_data
from app.database.session import check_database, get_db, session_scope

logger = logging.getLogger("specguard")

_SAFE_TRACE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

class AIStatus(BaseModel):
    """Configuration status of the selected AI provider (no secrets)."""

    provider: str
    model: str | None
    configured: bool
    issues: list[str] = Field(default_factory=list)

class HealthResponse(BaseModel):
    """Response body of ``GET /health``."""

    status: Literal["ok", "degraded"]
    app: str
    environment: str
    database: Literal["ok", "unavailable"]
    ai: AIStatus

class VersionResponse(BaseModel):
    """Response body of ``GET /version``."""

    name: str
    version: str
    api_version: str
    environment: str
    ai_provider: str
    ai_model: str | None

def configure_logging(level: str) -> None:
    """Configure root logging once and set the SpecGuard logger level."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    logging.getLogger("specguard").setLevel(level)

def resolve_trace_id(candidate: str | None) -> str:
    """Reuse a safe incoming trace ID, otherwise generate a new one."""
    if candidate and _SAFE_TRACE_ID.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex

def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        tables = init_db()
        logger.info(
            "Database ready at %s (%d tables)", settings.resolved_database_url, len(tables)
        )
        with session_scope() as session:
            report = seed_reference_data(session)
        logger.info(
            "Reference data: %d policies created, %d present; %d SUT versions created, %d present",
            report.policies_created,
            report.policies_existing,
            report.sut_versions_created,
            report.sut_versions_existing,
        )
        logger.info(
            "AI provider: %s, model: %s",
            settings.ai_provider,
            settings.active_ai_model or "<not set>",
        )
        for issue in settings.ai_configuration_issues():
            logger.warning("AI configuration issue: %s", issue)
        yield
        logger.info("SpecGuard shutting down")

    app = FastAPI(
        title=settings.app_name,
        version=APP_VERSION,
        description=(
            "Requirements Intelligence and Executable Quality platform for workforce "
            "software. The AI drafts specifications; deterministic code computes expected "
            "results, validates and executes tests; humans approve."
        ),
        debug=settings.debug,
        lifespan=lifespan,
        responses={
            422: {"model": ErrorResponse, "description": "Validation error"},
            500: {"model": ErrorResponse, "description": "Unexpected error"},
        },
    )
    app.state.settings = settings

    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[TRACE_HEADER],
    )

    @app.middleware("http")
    async def trace_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Attach a trace ID to every request, response and log line."""
        trace_id = resolve_trace_id(request.headers.get(TRACE_HEADER))
        request.state.trace_id = trace_id
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers[TRACE_HEADER] = trace_id
        logger.info(
            "%s %s -> %d (%.1f ms) trace=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            trace_id,
        )
        return response

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["system"],
        summary="Service health",
        responses={503: {"model": HealthResponse, "description": "Database unavailable"}},
    )
    def health(
        response: Response,
        db: Session = Depends(get_db),
        current: Settings = Depends(get_settings),
    ) -> HealthResponse:
        """Report database reachability and AI provider configuration status."""
        try:
            database_ok = check_database(db)
        except SQLAlchemyError:
            logger.exception("Database health check failed")
            database_ok = False

        issues = current.ai_configuration_issues()
        ai_status = AIStatus(
            provider=current.ai_provider,
            model=current.active_ai_model,
            configured=not issues,
            issues=issues,
        )
        if not database_ok:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return HealthResponse(
            status="ok" if database_ok and not issues else "degraded",
            app=current.app_name,
            environment=current.app_env,
            database="ok" if database_ok else "unavailable",
            ai=ai_status,
        )

    @app.get(
        "/version",
        response_model=VersionResponse,
        tags=["system"],
        summary="Application and API version",
    )
    def version(current: Settings = Depends(get_settings)) -> VersionResponse:
        """Return version information and the active AI provider (never credentials)."""
        return VersionResponse(
            name=current.app_name,
            version=APP_VERSION,
            api_version=API_VERSION,
            environment=current.app_env,
            ai_provider=current.ai_provider,
            ai_model=current.active_ai_model,
        )

    app.include_router(requirements.router)
    app.include_router(policies.router)
    app.include_router(specs.analysis_router)
    app.include_router(specs.ambiguity_router)
    app.include_router(specs.router)
    app.include_router(tests.spec_tests_router)
    app.include_router(tests.review_router)
    app.include_router(runs.runs_router)
    app.include_router(runs.defects_router)
    app.include_router(impact.router)
    app.include_router(dashboard.router)

    return app

app = create_app()
