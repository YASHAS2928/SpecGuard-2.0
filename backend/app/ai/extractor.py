"""Validated requirement extraction with retry and deterministic fallback."""

from __future__ import annotations

from collections.abc import Sequence

from app.ai.completion import CompletionClient
from app.ai.prompts import PROMPT_VERSION, extraction_prompt, policies_payload
from app.ai.schemas import AIResult
from app.ai.structured import run_structured
from app.core.contracts import AIProvider, PolicyResponse, RequirementExtraction


def extract_requirement(
    client: CompletionClient,
    *,
    provider: AIProvider,
    model: str | None,
    requirement_text: str,
    policies: Sequence[PolicyResponse],
    max_retries: int,
) -> AIResult[RequirementExtraction]:
    """Extract a requirement, retrying with validation feedback.

    Raises ``AIProviderError`` or ``AIOutputInvalidError``; never falls back to
    another provider or to canned data.
    """
    if not requirement_text.strip():
        raise ValueError("requirement_text must not be empty.")
    outcome = run_structured(
        client,
        extraction_prompt(requirement_text, policies_payload(policies)),
        RequirementExtraction,
        max_retries=max_retries,
    )
    return AIResult(
        data=outcome.data,
        provider=provider,
        model=model,
        prompt_version=PROMPT_VERSION,
        valid_first_try=outcome.valid_first_try,
        retries=outcome.retries,
        latency_ms=outcome.latency_ms,
        tokens_in=outcome.tokens_in,
        tokens_out=outcome.tokens_out,
    )
