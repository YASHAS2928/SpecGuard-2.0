"""Hosted open-weight provider (``AI_PROVIDER=hosted_open_weight``).

Talks to any OpenAI-compatible ``/chat/completions`` endpoint. Requirement text
is sent to that host, so only enable it when company policy allows it.
Loaded lazily by the factory.
"""

from __future__ import annotations

import httpx

from app.ai.client_provider import ClientBackedProvider
from app.ai.clients import OpenAICompatibleClient
from app.core.config import Settings
from app.core.contracts import AIProvider


class HostedOpenWeightProvider(ClientBackedProvider):
    provider = AIProvider.HOSTED_OPEN_WEIGHT

    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        # guaranteed by ai_configuration_issues()
        assert settings.hosted_open_weight_base_url is not None
        assert settings.hosted_open_weight_api_key is not None
        assert settings.hosted_open_weight_model is not None
        self.model = settings.hosted_open_weight_model
        super().__init__(
            OpenAICompatibleClient(
                base_url=settings.hosted_open_weight_base_url,
                api_key=settings.hosted_open_weight_api_key.get_secret_value(),
                model=settings.hosted_open_weight_model,
                timeout_seconds=settings.ai_timeout_seconds,
                transport=transport,
            ),
            settings.ai_max_retries,
        )
