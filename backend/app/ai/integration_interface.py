"""The frozen AI interface (owned by the tech lead, implemented by Member 3).

Every provider (Groq, Gemini, fake) must satisfy ``RequirementAI``:

* The constructor takes one argument: ``app.core.config.Settings``.
* ``extract_requirement`` returns a ``RequirementExtraction`` that already
  passed Pydantic validation, after at most ``settings.ai_max_retries`` retries.
  On a retry, send the validation errors back to the model.
* Errors: raise ``AIProviderError`` (network, rate limit, 5xx, timeout) or
  ``AIOutputInvalidError`` (output still invalid after retries). Put
  ``{"retries": n}`` in ``details`` when known.
* Never log or return API keys or raw prompts.
* Providers never fall back to another provider or to canned data.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.ai.schemas import AIResult, EdgeCaseSuggestion
from app.core.contracts import AIProvider, PolicyResponse, RequirementExtraction, SpecResponse


@runtime_checkable
class RequirementAI(Protocol):
    """Provider-independent AI operations used by the backend."""

    provider: AIProvider
    model: str | None

    def extract_requirement(
        self, *, requirement_text: str, policies: Sequence[PolicyResponse]
    ) -> AIResult[RequirementExtraction]:
        """Extract rules, inputs, ambiguities and assumptions from a requirement.

        ``source_span`` values must be copied word for word from the requirement
        text or from one of the supplied policies.
        """

    def suggest_edge_cases(self, *, spec: SpecResponse) -> AIResult[list[EdgeCaseSuggestion]]:
        """Suggest extra test scenarios for an approved specification."""
