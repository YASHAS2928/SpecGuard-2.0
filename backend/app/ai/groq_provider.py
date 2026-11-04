"""Groq provider (``AI_PROVIDER=groq``). Loaded lazily by the factory.

A thin configuration of the shared OpenAI-compatible client: Groq serves the same chat-completions
protocol as the hosted open-weight provider. Prompts, validation, retries (with the Pydantic errors fed
back), 429/5xx handling and error hygiene all live in the shared code paths. The key comes from
``GROQ_API_KEY`` and the model from ``GROQ_MODEL``; nothing is hardcoded except the public endpoint.
"""

from __future__ import annotations

import httpx

from app.ai.client_provider import ClientBackedProvider
from app.ai.clients import OpenAICompatibleClient
from app.core.config import Settings
from app.core.contracts import AIProvider

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(ClientBackedProvider):
    provider = AIProvider.GROQ

    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        # guaranteed by ai_configuration_issues()
        assert settings.groq_api_key is not None and settings.groq_model is not None
        self.model = settings.groq_model
        super().__init__(
            OpenAICompatibleClient(
                base_url=GROQ_BASE_URL,
                api_key=settings.groq_api_key.get_secret_value(),
                model=settings.groq_model,
                timeout_seconds=settings.ai_timeout_seconds,
                transport=transport,
            ),
            settings.ai_max_retries,
        )
