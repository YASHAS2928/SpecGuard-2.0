"""Development-only mock Time-to-Pay API. Start with uvicorn on port 9000."""

import os
import re
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, field_validator

from .calculator import VERSIONS, calculate, meal_minimum

app = FastAPI(title="Synthetic Time-to-Pay API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173", "http://localhost:5173",
        "http://127.0.0.1:5174", "http://localhost:5174",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)
TIME_PATTERN = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z")
LOOPBACK_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}
_selected_version: str | None = None  # set by POST /admin/version; overrides MOCK_VERSION


def current_version() -> str:
    """Runtime selection first, then the MOCK_VERSION environment variable, then 1.4.0."""
    return _selected_version or os.getenv("MOCK_VERSION", "1.4.0")


class VersionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str


def _require_loopback(request: Request) -> None:
    if request.client is None or request.client.host not in LOOPBACK_CLIENTS:
        raise HTTPException(403, detail="admin endpoints are loopback-only")


def _meal_minimum_or_503() -> int:
    try:
        return meal_minimum()
    except ValueError:
        raise HTTPException(503, detail="invalid MOCK_MEAL_MIN configuration") from None


@app.get("/version")
def version_info() -> dict[str, object]:
    """The implementation served now and the shortest recorded meal break that is deducted."""
    return {"version": current_version(), "meal_minimum": _meal_minimum_or_503(), "available": sorted(VERSIONS)}


@app.get("/admin/version")
def get_version(request: Request) -> dict[str, object]:
    """Development-only: the implementation version currently served."""
    _require_loopback(request)
    return {"version": current_version(), "available": sorted(VERSIONS)}


@app.post("/admin/version")
def select_version(selection: VersionSelection, request: Request) -> dict[str, object]:
    """Development-only: switch the served implementation without restarting."""
    global _selected_version
    _require_loopback(request)
    if selection.version not in VERSIONS:
        raise HTTPException(422, detail="unsupported mock version")
    _selected_version = selection.version
    return {"version": _selected_version, "available": sorted(VERSIONS)}


@app.delete("/admin/version")
def clear_version(request: Request) -> dict[str, object]:
    """Development-only: drop the runtime selection and return to MOCK_VERSION (or 1.4.0)."""
    global _selected_version
    _require_loopback(request)
    _selected_version = None
    return {"version": current_version(), "available": sorted(VERSIONS)}


class PayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_time: str
    end_time: str
    overnight: StrictBool
    meal_break_minutes: StrictInt

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_time(cls, value: str) -> str:
        if not TIME_PATTERN.fullmatch(value):
            raise ValueError("time must be HH:MM in 24-hour format")
        return value


def _minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return 60 * hour + minute


@app.post("/v1/pay/calculate")
def calculate_pay(request: PayRequest, response: Response) -> dict[str, int]:
    start, end = _minutes(request.start_time), _minutes(request.end_time)
    if start == end:
        raise HTTPException(422, detail="equal times are ambiguous")
    if request.overnight and end > start:
        raise HTTPException(422, detail="overnight indicator requires midnight crossing")
    if not request.overnight and end < start:
        raise HTTPException(422, detail="earlier end requires overnight indicator")
    span = end - start + (1440 if request.overnight else 0)
    if span > 960:
        raise HTTPException(422, detail="shift exceeds 960 minutes")
    if request.meal_break_minutes < 0 or request.meal_break_minutes > span:
        raise HTTPException(422, detail="invalid meal break duration")
    version = current_version()
    if version not in VERSIONS:
        raise HTTPException(503, detail="unsupported configured mock version")
    response.headers["X-Mock-Version"] = version
    return calculate(version, start, end, request.overnight, request.meal_break_minutes,
                     _meal_minimum_or_503())
