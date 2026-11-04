"""Test design, listing and review endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.core.contracts import (
    DesignTestsRequest,
    DesignTestsResponse,
    ErrorResponse,
    TestCaseResponse,
    TestOrigin,
    TestReviewRequest,
    TestReviewResponse,
    TestStatus,
    TestTechnique,
)
from app.core.dependencies import DbSession, Engine, OptionalAI, TraceId
from app.services import test_service

spec_tests_router = APIRouter(prefix="/specs", tags=["tests"])
review_router = APIRouter(prefix="/tests", tags=["tests"])


@spec_tests_router.post(
    "/{spec_id}/design-tests", response_model=DesignTestsResponse, summary="Design and validate tests",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
               503: {"model": ErrorResponse}},
)
def design_tests_endpoint(
    spec_id: uuid.UUID, payload: DesignTestsRequest, db: DbSession, engine: Engine, ai: OptionalAI,
    trace_id: TraceId,
) -> DesignTestsResponse:
    """Engine tests with oracle expected values, plus optional AI edge cases; every test is validated."""
    return test_service.design_tests(db, spec_id, payload, engine=engine, ai=ai, trace_id=trace_id)


@spec_tests_router.get(
    "/{spec_id}/tests", response_model=list[TestCaseResponse], summary="List the tests of a specification",
    responses={404: {"model": ErrorResponse}},
)
def list_tests_endpoint(
    spec_id: uuid.UUID, db: DbSession, status: TestStatus | None = None,
    technique: TestTechnique | None = None, origin: TestOrigin | None = None,
) -> list[TestCaseResponse]:
    return test_service.list_tests(db, spec_id, status=status, technique=technique, origin=origin)


@review_router.post(
    "/review", response_model=TestReviewResponse, summary="Approve or reject tests",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def review_tests_endpoint(payload: TestReviewRequest, db: DbSession, trace_id: TraceId) -> TestReviewResponse:
    """Partial success is allowed; every refusal is explained."""
    return test_service.review_tests(db, payload, trace_id=trace_id)
