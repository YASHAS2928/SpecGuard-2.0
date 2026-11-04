"""Endpoints for requirement analysis, ambiguity resolution and specifications."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.core.contracts import (
    AnalyzeRequirementRequest,
    AnalyzeRequirementResponse,
    ApproveSpecRequest,
    ErrorResponse,
    ResolveAmbiguityRequest,
    SpecResponse,
)
from app.core.dependencies import AI, DbSession, SpecCheckerDep, TraceId
from app.services import spec_service

analysis_router = APIRouter(prefix="/requirement-versions", tags=["analysis"])
ambiguity_router = APIRouter(prefix="/ambiguities", tags=["analysis"])
router = APIRouter(prefix="/specs", tags=["specs"])


@analysis_router.post(
    "/{version_id}/analyze",
    response_model=AnalyzeRequirementResponse,
    summary="Analyse a requirement version with the configured AI provider",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def analyze_endpoint(
    version_id: uuid.UUID,
    payload: AnalyzeRequirementRequest,
    db: DbSession,
    ai: AI,
    checker: SpecCheckerDep,
    trace_id: TraceId,
) -> AnalyzeRequirementResponse:
    """Extract rules and ambiguities, run the grounding check and store a DRAFT spec."""
    return spec_service.analyze_requirement_version(
        db, version_id, payload, ai=ai, checker=checker, trace_id=trace_id
    )


@analysis_router.get(
    "/{version_id}/specs",
    response_model=list[SpecResponse],
    summary="List the specifications of a requirement version",
    responses={404: {"model": ErrorResponse}},
)
def list_specs_endpoint(version_id: uuid.UUID, db: DbSession) -> list[SpecResponse]:
    """Return every specification drafted for this requirement version, oldest first."""
    return spec_service.list_specs_for_version(db, version_id)


@ambiguity_router.post(
    "/{ambiguity_id}/resolve",
    response_model=SpecResponse,
    summary="Resolve or defer an ambiguity",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def resolve_endpoint(
    ambiguity_id: uuid.UUID,
    payload: ResolveAmbiguityRequest,
    db: DbSession,
    trace_id: TraceId,
) -> SpecResponse:
    """Apply the chosen option's patch to the DRAFT specification, or defer the question."""
    return spec_service.resolve_ambiguity(db, ambiguity_id, payload, trace_id=trace_id)


@router.get(
    "/{spec_id}",
    response_model=SpecResponse,
    summary="Get a specification",
    responses={404: {"model": ErrorResponse}},
)
def get_spec_endpoint(spec_id: uuid.UUID, db: DbSession) -> SpecResponse:
    """Return one specification with rules, ambiguities and active validation issues."""
    return spec_service.get_spec(db, spec_id)


@router.post(
    "/{spec_id}/approve",
    response_model=SpecResponse,
    summary="Approve a specification",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def approve_endpoint(
    spec_id: uuid.UUID, payload: ApproveSpecRequest, db: DbSession, trace_id: TraceId
) -> SpecResponse:
    """Approve a DRAFT spec; blocked while ambiguities, parameters or checks are unresolved."""
    return spec_service.approve_spec(db, spec_id, payload, trace_id=trace_id)
