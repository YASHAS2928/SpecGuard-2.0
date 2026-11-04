"""Development-only mock Time-to-Pay API. Start with uvicorn on port 9000."""

import os
import re
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, field_validator

from .calculator import VERSIONS, calculate

app = FastAPI(title="Synthetic Time-to-Pay API")
TIME_PATTERN = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z")


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
    version = os.getenv("MOCK_VERSION", "1.4.0")
    if version not in VERSIONS:
        raise HTTPException(503, detail="unsupported configured mock version")
    response.headers["X-Mock-Version"] = version
    return calculate(version, start, end, request.overnight, request.meal_break_minutes)
