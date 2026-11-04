"""Validated requirement extraction with retry and deterministic fallback."""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from app.core.contracts import RequirementExtraction

from .adapter import CompletionProvider, ProviderError
from .fake_provider import FakeProvider
from .prompts import PROMPT_VERSION, extraction_prompt


@dataclass(frozen=True)
class ExtractionResult:
    extraction: RequirementExtraction
    provider: str
    model: str | None
    prompt_version: str
    valid_first_try: bool
    retries: int
    fallback_used: bool
    latency_ms: int


def _parse_completion(text: str) -> RequirementExtraction:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("Provider output was not valid JSON.") from error
    try:
        return RequirementExtraction.model_validate(payload)
    except ValidationError as error:
        raise ValueError("Provider output did not match RequirementExtraction.") from error


def extract_requirement(
    requirement_text: str,
    policies: list[dict[str, Any]],
    provider: CompletionProvider,
    *,
    max_retries: int = 1,
) -> ExtractionResult:
    """Extract a requirement, retry once, then use the fake provider."""
    if not isinstance(requirement_text, str) or not requirement_text.strip():
        raise ValueError("requirement_text must not be empty.")
    if max_retries < 0 or max_retries > 1:
        raise ValueError("max_retries must be 0 or 1.")

    prompt = extraction_prompt(requirement_text, policies)
    started = perf_counter()
    attempts = 0
    while attempts <= max_retries:
        try:
            completion = provider.complete(prompt)
            extraction = _parse_completion(completion.text)
            return ExtractionResult(
                extraction=extraction,
                provider=completion.provider,
                model=completion.model,
                prompt_version=PROMPT_VERSION,
                valid_first_try=attempts == 0,
                retries=attempts,
                fallback_used=False,
                latency_ms=round((perf_counter() - started) * 1000),
            )
        except (ProviderError, ValueError, ValidationError, json.JSONDecodeError) as error:
            attempts += 1

    try:
        completion = FakeProvider().complete(prompt)
        extraction = _parse_completion(completion.text)
    except (ProviderError, ValueError, ValidationError, json.JSONDecodeError) as error:
        raise RuntimeError("AI extraction failed and fake fallback was unavailable.") from error
    return ExtractionResult(
        extraction=extraction,
        provider=completion.provider,
        model=completion.model,
        prompt_version=PROMPT_VERSION,
        valid_first_try=False,
        retries=attempts,
        fallback_used=True,
        latency_ms=round((perf_counter() - started) * 1000),
    )
