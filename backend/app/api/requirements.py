"""Requirement and requirement-version endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.contracts import (
    ErrorResponse,
    RequirementCreate,
    RequirementResponse,
    RequirementVersionCreate,
    RequirementVersionResponse,
)
from app.core.dependencies import DbSession, TraceId
from app.services import requirement_service

router = APIRouter(prefix="/requirements", tags=["requirements"])


@router.post(
    "",
    response_model=RequirementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a requirement with version 1",
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def create_requirement_endpoint(
    payload: RequirementCreate, db: DbSession, trace_id: TraceId
) -> RequirementResponse:
    """Create a requirement in DRAFT status with its first immutable version."""
    requirement = requirement_service.create_requirement(db, payload, trace_id=trace_id)
    return RequirementResponse.model_validate(requirement)


@router.get(
    "",
    response_model=list[RequirementResponse],
    summary="List requirements",
)
def list_requirements_endpoint(db: DbSession) -> list[RequirementResponse]:
    """Return all requirements with their versions, ordered by code."""
    return [RequirementResponse.model_validate(r) for r in requirement_service.list_requirements(db)]


@router.get(
    "/{requirement_id}",
    response_model=RequirementResponse,
    summary="Get a requirement with all versions",
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def get_requirement_endpoint(requirement_id: uuid.UUID, db: DbSession) -> RequirementResponse:
    """Return one requirement and all of its versions (oldest first)."""
    return RequirementResponse.model_validate(requirement_service.get_requirement(db, requirement_id))


@router.post(
    "/{requirement_id}/versions",
    response_model=RequirementVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create the next requirement version",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def create_version_endpoint(
    requirement_id: uuid.UUID,
    payload: RequirementVersionCreate,
    db: DbSession,
    trace_id: TraceId,
) -> RequirementVersionResponse:
    """Append an immutable version. Approved requirements move to CHANGED status."""
    version = requirement_service.create_version(db, requirement_id, payload, trace_id=trace_id)
    return RequirementVersionResponse.model_validate(version)
