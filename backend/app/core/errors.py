"""Typed API errors and exception handlers producing the standard error envelope.

Every error response has the shape::

    {"error": {"code": "...", "message": "...", "details": ..., "trace_id": "..."}}

Services raise subclasses of ``ApiError``; they never build HTTP responses.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.contracts import ErrorBody, ErrorCode, ErrorResponse

logger = logging.getLogger("specguard.errors")

TRACE_HEADER = "X-Trace-ID"


class ApiError(Exception):
    """Base class for errors that map to a specific HTTP status and error code."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: ErrorCode = ErrorCode.VALIDATION_ERROR

    def __init__(
        self,
        message: str,
        *,
        details: Any = None,
        code: ErrorCode | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    code = ErrorCode.NOT_FOUND


class ForbiddenError(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    code = ErrorCode.FORBIDDEN


class ConflictError(ApiError):
    status_code = status.HTTP_409_CONFLICT
    code = ErrorCode.CONFLICT


class StateTransitionError(ApiError):
    status_code = status.HTTP_409_CONFLICT
    code = ErrorCode.STATE_TRANSITION_NOT_ALLOWED


class SpecNotApprovableError(ApiError):
    status_code = status.HTTP_409_CONFLICT
    code = ErrorCode.SPEC_NOT_APPROVABLE


class TestNotApprovableError(ApiError):
    status_code = status.HTTP_409_CONFLICT
    code = ErrorCode.TEST_NOT_APPROVABLE


class AIProviderNotConfiguredError(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = ErrorCode.AI_PROVIDER_NOT_CONFIGURED


class AIProviderError(ApiError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = ErrorCode.AI_PROVIDER_ERROR


class AIOutputInvalidError(ApiError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = ErrorCode.AI_OUTPUT_INVALID


class IntegrationUnavailableError(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = ErrorCode.INTEGRATION_UNAVAILABLE


_HTTP_STATUS_CODES: dict[int, ErrorCode] = {
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
}


def _trace_id(request: Request) -> str:
    """Return the request's trace ID, generating one if middleware did not run."""
    trace_id = getattr(request.state, "trace_id", None)
    if not trace_id:
        trace_id = uuid.uuid4().hex
        request.state.trace_id = trace_id
    return str(trace_id)


def error_response(
    request: Request,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: Any = None,
) -> JSONResponse:
    """Build a JSON response in the standard error envelope."""
    trace_id = _trace_id(request)
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details, trace_id=trace_id)
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers={TRACE_HEADER: trace_id},
    )


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle ``ApiError`` and its subclasses."""
    assert isinstance(exc, ApiError)
    logger.info("API error %s (%d): %s", exc.code, exc.status_code, exc.message)
    return error_response(request, exc.status_code, exc.code, exc.message, exc.details)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle framework HTTP errors such as unknown routes or wrong methods."""
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_STATUS_CODES.get(exc.status_code, ErrorCode.HTTP_ERROR)
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error."
    return error_response(request, exc.status_code, code, message)


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle request validation errors without echoing submitted values."""
    assert isinstance(exc, RequestValidationError)
    details = [
        {"loc": [str(part) for part in err.get("loc", ())], "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        ErrorCode.VALIDATION_ERROR,
        "Request validation failed.",
        details,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected errors without leaking internal details."""
    trace_id = _trace_id(request)
    logger.error("Unhandled error trace=%s: %s", trace_id, type(exc).__name__, exc_info=exc)
    return error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCode.INTERNAL_ERROR,
        "An unexpected error occurred. Quote the trace ID when reporting it.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all SpecGuard exception handlers to the application."""
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
