"""Run and defect endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.contracts import DefectResponse, DefectStatus, ErrorResponse, RunCreateRequest, RunResponse
from app.core.dependencies import AppSettings, DbSession, Engine, TraceId
from app.services import run_service

runs_router = APIRouter(prefix="/runs", tags=["runs"])
defects_router = APIRouter(prefix="/defects", tags=["runs"])


@runs_router.post(
    "", response_model=RunResponse, status_code=status.HTTP_201_CREATED, summary="Run approved tests",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
               503: {"model": ErrorResponse}},
)
def create_run_endpoint(
    payload: RunCreateRequest, db: DbSession, engine: Engine, settings: AppSettings, trace_id: TraceId,
) -> RunResponse:
    """Run APPROVED tests against the loopback mock API; unreachable targets give ERROR results."""
    return run_service.create_run(db, payload, engine=engine, settings=settings, trace_id=trace_id)


@runs_router.get("/{run_id}", response_model=RunResponse, summary="Get a run",
                 responses={404: {"model": ErrorResponse}})
def get_run_endpoint(run_id: uuid.UUID, db: DbSession) -> RunResponse:
    return run_service.get_run(db, run_id)


@defects_router.get("", response_model=list[DefectResponse], summary="List defects")
def list_defects_endpoint(
    db: DbSession, status: DefectStatus | None = None, spec_id: uuid.UUID | None = None,
) -> list[DefectResponse]:
    return run_service.list_defects(db, status=status, spec_id=spec_id)
