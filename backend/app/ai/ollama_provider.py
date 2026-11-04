"""Local Ollama provider (``AI_PROVIDER=ollama``). Loaded lazily by the factory."""

from __future__ import annotations

import httpx

from app.ai.client_provider import ClientBackedProvider
from app.ai.clients import OllamaClient
from app.core.config import Settings
from app.core.contracts import AIProvider


class OllamaProvider(ClientBackedProvider):
    provider = AIProvider.OLLAMA

    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        assert settings.ollama_model is not None  # guaranteed by ai_configuration_issues()
        self.model = settings.ollama_model
        super().__init__(
            OllamaClient(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                timeout_seconds=settings.ai_timeout_seconds,
                transport=transport,
            ),
            settings.ai_max_retries,
        )
