"""Validated structured output with retries and honest failure reporting.

The model's text must parse into the requested Pydantic contract. On a retry
the validation errors (location and message only, never the model's output) are
sent back. After the retries are used up the failure is raised as an API error;
there is no fallback to another provider or to canned data.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.completion import CompletionClient, CompletionError
from app.core.errors import AIOutputInvalidError, AIProviderError

M = TypeVar("M", bound=BaseModel)

_MAX_ERRORS = 10
_MAX_MESSAGE_LENGTH = 200


@dataclass(frozen=True)
class StructuredOutcome(Generic[M]):
    """A validated model plus call metadata."""

    data: M
    valid_first_try: bool
    retries: int
    latency_ms: int
    tokens_in: int | None
    tokens_out: int | None


def summarise_errors(exc: ValidationError) -> list[dict[str, str]]:
    """Return location and message of validation errors, never the submitted values."""
    return [
        {
            "loc": ".".join(str(part) for part in error["loc"]),
            "msg": error["msg"][:_MAX_MESSAGE_LENGTH],
        }
        for error in exc.errors()[:_MAX_ERRORS]
    ]


def _retry_prompt(prompt: str, errors: list[dict[str, str]]) -> str:
    lines = "\n".join(f"- {item['loc'] or 'output'}: {item['msg']}" for item in errors)
    return (
        f"{prompt}\n"
        "Your previous answer was rejected by validation:\n"
        f"{lines}\n"
        "Return corrected JSON only."
    )


def _add(total: int | None, value: int | None) -> int | None:
    if value is None:
        return total
    return value if total is None else total + value


def run_structured(
    client: CompletionClient,
    prompt: str,
    model_type: type[M],
    *,
    max_retries: int,
) -> StructuredOutcome[M]:
    """Complete ``prompt`` until the output validates as ``model_type``.

    Raises ``AIProviderError`` if the last attempt could not reach the backend
    and ``AIOutputInvalidError`` if the last attempt returned invalid output.
    Both carry ``details={"retries": n}``.
    """
    if max_retries < 0:
        raise ValueError("max_retries must not be negative.")

    started = time.perf_counter()
    tokens_in: int | None = None
    tokens_out: int | None = None
    current_prompt = prompt
    provider_error: CompletionError | None = None
    invalid_errors: list[dict[str, str]] = []

    for attempt in range(max_retries + 1):
        try:
            completion = client.complete(current_prompt)
        except CompletionError as exc:
            provider_error = exc
            continue
        provider_error = None
        tokens_in = _add(tokens_in, completion.tokens_in)
        tokens_out = _add(tokens_out, completion.tokens_out)
        try:
            data = model_type.model_validate_json(completion.text)
        except ValidationError as exc:
            invalid_errors = summarise_errors(exc)
            current_prompt = _retry_prompt(prompt, invalid_errors)
            continue
        return StructuredOutcome(
            data=data,
            valid_first_try=attempt == 0,
            retries=attempt,
            latency_ms=int((time.perf_counter() - started) * 1000),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    details = {"retries": max_retries}
    if provider_error is not None:
        raise AIProviderError(str(provider_error), details=details) from provider_error
    raise AIOutputInvalidError(
        "The AI provider's output was still invalid after retrying.",
        details={**details, "errors": invalid_errors},
    )
