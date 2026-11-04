"""Provider base: turns any ``CompletionClient`` into a ``RequirementAI``."""

from __future__ import annotations

from collections.abc import Sequence

from app.ai import edge_cases, extractor
from app.ai.completion import CompletionClient
from app.ai.schemas import AIResult, EdgeCaseSuggestion
from app.core.contracts import AIProvider, PolicyResponse, RequirementExtraction, SpecResponse


class ClientBackedProvider:
    """Implements ``RequirementAI`` on top of a completion client.

    Subclasses set ``provider`` and ``model`` and supply the client. Retries
    come from ``Settings.ai_max_retries``. Failures surface as
    ``AIProviderError`` / ``AIOutputInvalidError``; nothing is faked.
    """

    provider: AIProvider
    model: str | None

    def __init__(self, client: CompletionClient, max_retries: int) -> None:
        self._client = client
        self._max_retries = max_retries

    def extract_requirement(
        self, *, requirement_text: str, policies: Sequence[PolicyResponse]
    ) -> AIResult[RequirementExtraction]:
        return extractor.extract_requirement(
            self._client,
            provider=self.provider,
            model=self.model,
            requirement_text=requirement_text,
            policies=policies,
            max_retries=self._max_retries,
        )

    def suggest_edge_cases(self, *, spec: SpecResponse) -> AIResult[list[EdgeCaseSuggestion]]:
        return edge_cases.suggest_edge_cases(
            self._client,
            provider=self.provider,
            model=self.model,
            spec=spec,
            max_retries=self._max_retries,
        )
