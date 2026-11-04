"""AI-layer edge-case suggestions; expected values remain oracle-owned."""

from __future__ import annotations

from pydantic import Field

from app.ai.completion import CompletionClient
from app.ai.prompts import EDGE_CASE_PROMPT_VERSION, edge_case_prompt
from app.ai.schemas import AIResult, EdgeCaseSuggestion
from app.ai.structured import run_structured
from app.core.contracts import AIProvider, ContractModel, SpecResponse


class EdgeCaseList(ContractModel):
    """Envelope a model returns: a JSON object cannot be a bare array in JSON mode."""

    suggestions: list[EdgeCaseSuggestion] = Field(min_length=1, max_length=10)


def suggest_edge_cases(
    client: CompletionClient,
    *,
    provider: AIProvider,
    model: str | None,
    spec: SpecResponse,
    max_retries: int,
) -> AIResult[list[EdgeCaseSuggestion]]:
    """Ask the model for extra scenarios, retrying with validation feedback."""
    outcome = run_structured(
        client, edge_case_prompt(spec), EdgeCaseList, max_retries=max_retries
    )
    return AIResult(
        data=outcome.data.suggestions,
        provider=provider,
        model=model,
        prompt_version=EDGE_CASE_PROMPT_VERSION,
        valid_first_try=outcome.valid_first_try,
        retries=outcome.retries,
        latency_ms=outcome.latency_ms,
        tokens_in=outcome.tokens_in,
        tokens_out=outcome.tokens_out,
    )
