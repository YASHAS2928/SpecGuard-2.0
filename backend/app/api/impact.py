"""Change-impact endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.contracts import ChangeImpactRequest, ChangeImpactResponse, ErrorResponse
from app.core.dependencies import DbSession, Engine, TraceId
from app.services import impact_service

router = APIRouter(prefix="/specs", tags=["impact"])


@router.post(
    "/{new_spec_id}/impact", response_model=ChangeImpactResponse, status_code=status.HTTP_201_CREATED,
    summary="Analyse the impact of a specification change",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
               503: {"model": ErrorResponse}},
)
def analyze_impact_endpoint(
    new_spec_id: uuid.UUID, payload: ChangeImpactRequest, db: DbSession, engine: Engine, trace_id: TraceId,
) -> ChangeImpactResponse:
    """``from_spec`` may be APPROVED or SUPERSEDED; the new spec must be APPROVED."""
    return impact_service.analyze_impact(db, new_spec_id, payload, engine=engine, trace_id=trace_id)
