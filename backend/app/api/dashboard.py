"""Dashboard metrics and audit trail endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.contracts import AuditAction, AuditPage, EntityType, MetricsOverviewResponse
from app.core.dependencies import DbSession
from app.services import metrics_service

router = APIRouter(tags=["dashboard"])


@router.get("/metrics/overview", response_model=MetricsOverviewResponse, summary="Dashboard metrics")
def overview_endpoint(db: DbSession) -> MetricsOverviewResponse:
    """Every value is computed from database rows; ratios are null when the denominator is 0."""
    return metrics_service.overview(db)


@router.get("/audit", response_model=AuditPage, summary="Audit trail")
def audit_endpoint(
    db: DbSession,
    entity_type: EntityType | None = None,
    entity_id: uuid.UUID | None = None,
    action: AuditAction | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPage:
    return metrics_service.list_audit(db, entity_type=entity_type, entity_id=entity_id, action=action,
                                      limit=limit, offset=offset)
