"""Groq provider (thin OpenAI-compatible configuration) and the gemini 'not implemented' message."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest

from app.ai.adapter import get_ai_provider
from app.ai.groq_provider import GROQ_BASE_URL, GroqProvider
from app.ai.integration_interface import RequirementAI
from app.core.config import Settings
from app.core.contracts import RQ014_EXTRACTION_EXAMPLE, AIProvider
from app.core.errors import AIOutputInvalidError, AIProviderError, AIProviderNotConfiguredError

KEY = "gsk_test_secret_key_value_98765"
TEXT = ("For an overnight shift, calculate overtime correctly after the employee has worked the configured "
        "number of paid hours, excluding the unpaid meal break.")


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"ai_provider": "groq", "groq_api_key": KEY, "groq_model": "model-from-settings",
                              "ai_max_retries": 1}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                     "usage": {"prompt_tokens": 5, "completion_tokens": 7}})


def provider(handler: Any, **overrides: Any) -> GroqProvider:
    return GroqProvider(settings(**overrides), transport=httpx.MockTransport(handler))


def test_the_factory_builds_a_groq_provider_from_settings() -> None:
    built = get_ai_provider(settings())
    assert isinstance(built, GroqProvider) and isinstance(built, RequirementAI)
    assert built.provider is AIProvider.GROQ and built.model == "model-from-settings"


def test_the_model_and_key_come_from_settings_and_the_endpoint_is_groqs_openai_compatible_one() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return reply(json.dumps(RQ014_EXTRACTION_EXAMPLE))

    result = provider(handler, groq_model="another-model").extract_requirement(requirement_text=TEXT, policies=[])
    request, body = seen[0], json.loads(seen[0].content)
    assert str(request.url) == f"{GROQ_BASE_URL}/chat/completions" == "https://api.groq.com/openai/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert body["model"] == "another-model" and body["temperature"] == 0.1
    assert body["response_format"] == {"type": "json_object"}
    assert result.provider is AIProvider.GROQ and result.model == "another-model" and result.valid_first_try is True
    assert (result.tokens_in, result.tokens_out) == (5, 7)


def test_invalid_output_is_retried_with_the_validation_errors_fed_back() -> None:
    prompts: list[str] = []
    answers = iter(["{}", json.dumps(RQ014_EXTRACTION_EXAMPLE)])

    def handler(request: httpx.Request) -> httpx.Response:
        prompts.append(json.loads(request.content)["messages"][0]["content"])
        return reply(next(answers))

    result = provider(handler).extract_requirement(requirement_text=TEXT, policies=[])
    assert result.retries == 1 and result.valid_first_try is False
    assert "rejected by validation" in prompts[1] and "rejected by validation" not in prompts[0]


def test_persistent_invalid_output_raises_and_never_falls_back() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return reply("not json")

    with pytest.raises(AIOutputInvalidError) as caught:
        provider(handler, ai_max_retries=2).extract_requirement(requirement_text=TEXT, policies=[])
    assert caught.value.details["retries"] == 2 and len(calls) == 3


def test_max_retries_and_timeout_come_from_settings() -> None:
    assert provider(lambda r: reply("{}"), ai_max_retries=0)._max_retries == 0
    assert provider(lambda r: reply("{}"), ai_max_retries=3)._max_retries == 3


@pytest.mark.parametrize(("status", "expected"), [(429, "rate limit"), (500, "HTTP 500"), (503, "HTTP 503"),
                                                  (401, "rejected the credentials")])
def test_http_errors_become_provider_errors_after_the_retries(status: int, expected: str) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, text=f"upstream body {KEY}")

    with pytest.raises(AIProviderError) as caught:
        provider(handler).extract_requirement(requirement_text=TEXT, policies=[])
    assert expected in caught.value.message and caught.value.details == {"retries": 1} and len(calls) == 2


def test_a_transient_rate_limit_then_success_is_retried() -> None:
    answers = iter([httpx.Response(429), reply(json.dumps(RQ014_EXTRACTION_EXAMPLE))])
    result = provider(lambda r: next(answers)).extract_requirement(requirement_text=TEXT, policies=[])
    assert result.retries == 1


def test_timeouts_and_network_errors_are_provider_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(AIProviderError, match="timed out"):
        provider(handler, ai_max_retries=0).extract_requirement(requirement_text=TEXT, policies=[])


def test_the_key_never_appears_in_errors_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"bad key {KEY} for {request.url}")

    with pytest.raises(AIProviderError) as caught:
        provider(handler).extract_requirement(requirement_text=TEXT, policies=[])
    assert KEY not in caught.value.message and KEY not in str(caught.value.details) and KEY not in caplog.text
    assert KEY not in repr(settings()) and KEY not in str(settings().model_dump())


def test_a_missing_key_or_model_is_a_clear_503_listing_the_variables() -> None:
    with pytest.raises(AIProviderNotConfiguredError) as caught:
        get_ai_provider(Settings(_env_file=None, ai_provider="groq"))
    joined = " ".join(caught.value.details["issues"])
    assert "GROQ_API_KEY" in joined and "GROQ_MODEL" in joined


@pytest.mark.parametrize("configured", [False, True])
def test_gemini_says_it_is_not_implemented_whether_or_not_it_is_configured(configured: bool) -> None:
    extra = {"gemini_api_key": "k", "gemini_model": "m"} if configured else {}
    with pytest.raises(AIProviderNotConfiguredError) as caught:
        get_ai_provider(Settings(_env_file=None, ai_provider="gemini", **extra))
    assert "gemini provider is not implemented in this build" in caught.value.message
    assert "groq" in caught.value.message and caught.value.details["supported"]
    assert "GEMINI_API_KEY" not in caught.value.message  # no misleading request for a key


def test_gemini_returns_503_through_the_api(client: Any) -> None:
    from app.core.config import get_settings

    client.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, ai_provider="gemini")
    created = client.post("/requirements", json={
        "code": "RQ-777001", "title": "Overnight overtime", "text": TEXT,
        "policy_ids": ["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"],
        "actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"})
    version_id = (created.json()["versions"][0]["id"] if created.status_code == 201
                  else client.get("/requirements").json()[-1]["versions"][0]["id"])
    response = client.post(f"/requirement-versions/{version_id}/analyze", json={"actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"})
    assert response.status_code == 503 and response.json()["error"]["code"] == "AI_PROVIDER_NOT_CONFIGURED"
    assert "not implemented in this build" in response.json()["error"]["message"]
