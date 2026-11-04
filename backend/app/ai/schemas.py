"""Result envelope and extra output contracts for AI providers.

``AIResult`` carries a provider's output plus the metadata the backend logs to
the ``llm_calls`` table. Hashes are computed by the backend, not by providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import Field

from app.core.contracts import (
    AIProvider,
    AIText,
    AssertionTemplate,
    ContractModel,
    ExpectedResult,
    RuleKey,
    ShortAIText,
    TestInputs,
)

T = TypeVar("T")


@dataclass(frozen=True)
class AIResult(Generic[T]):
    """A provider's validated output together with call metadata."""

    data: T
    provider: AIProvider
    model: str | None
    prompt_version: str
    valid_first_try: bool
    retries: int = 0
    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


class EdgeCaseSuggestion(ContractModel):
    """An AI-suggested extra test scenario.

    ``claimed_expected`` is only the model's claim. The deterministic oracle
    computes the real expected value, and a mismatch is flagged (V08).
    """

    title: ShortAIText
    rationale: AIText
    inputs: TestInputs
    assertion: AssertionTemplate
    claimed_expected: ExpectedResult | None = None
    rule_keys: list[RuleKey] = Field(default_factory=list, max_length=10)
