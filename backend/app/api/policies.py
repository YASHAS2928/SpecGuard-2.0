"""Policy registry endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.contracts import POLICY_CODE_PATTERN, ErrorResponse, PolicyResponse
from app.core.dependencies import DbSession
from app.services import policy_service

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get(
    "",
    response_model=list[PolicyResponse],
    summary="List policies, filtered by effective date",
    responses={422: {"model": ErrorResponse}},
)
def list_policies_endpoint(
    db: DbSession,
    effective_on: Annotated[
        date | None, Query(description="Return versions effective on this date (default: today, UTC).")
    ] = None,
    code: Annotated[
        str | None, Query(pattern=POLICY_CODE_PATTERN, description="Filter by policy code, e.g. POL-OT-01.")
    ] = None,
    include_all_versions: Annotated[
        bool, Query(description="Ignore the date filter and return every version.")
    ] = False,
) -> list[PolicyResponse]:
    """Return fictional policies, by default only versions effective today."""
    policies = policy_service.list_policies(
        db, effective_on=effective_on, code=code, include_all_versions=include_all_versions
    )
    return [PolicyResponse.model_validate(policy) for policy in policies]
