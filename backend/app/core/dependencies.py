"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.ai.adapter import get_ai_provider
from app.ai.integration_interface import RequirementAI
from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.services.integration_service import SpecChecker, get_spec_checker


def get_trace_id(request: Request) -> str | None:
    """Return the trace ID assigned by the trace middleware, if any."""
    trace_id = getattr(request.state, "trace_id", None)
    return str(trace_id) if trace_id else None


DbSession = Annotated[Session, Depends(get_db)]
TraceId = Annotated[str | None, Depends(get_trace_id)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_ai(settings: AppSettings) -> RequirementAI:
    """Return the configured AI provider (raises 503 if it is not configured)."""
    return get_ai_provider(settings)


AI = Annotated[RequirementAI, Depends(get_ai)]
SpecCheckerDep = Annotated[SpecChecker | None, Depends(get_spec_checker)]
