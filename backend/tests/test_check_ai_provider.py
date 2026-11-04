"""scripts/check_ai_provider.py: no network by default, one extraction with --live."""

from __future__ import annotations

import socket
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import AIProviderError
from scripts import check_ai_provider as script

KEY = "gsk_do_not_print_this_key_123"


@pytest.fixture()
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Fail loudly (and record) if anything tries to open a socket or send an HTTP request."""
    attempts: list[str] = []

    def blocked(*args: Any, **kwargs: Any) -> Any:
        attempts.append("network")
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(httpx.Client, "send", blocked)
    return attempts


def groq_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"ai_provider": "groq", "groq_api_key": KEY, "groq_model": "some-model"}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_default_run_prints_the_configuration_and_makes_no_network_call(
    no_network: list[str], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(script, "get_ai_provider", lambda *_: pytest.fail("the provider must not be built"))
    assert script.main([], groq_settings()) == 0
    out = capsys.readouterr().out
    assert "provider:   groq" in out and "model:      some-model" in out and "configured: yes" in out
    assert "no network call made" in out and KEY not in out and no_network == []


def test_default_run_reports_missing_configuration_with_exit_code_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert script.main([], Settings(_env_file=None, ai_provider="groq")) == 2
    out = capsys.readouterr().out
    assert "configured: no" in out and "GROQ_API_KEY" in out and "GROQ_MODEL" in out


def test_live_with_the_fake_provider_runs_one_extraction_offline(
    no_network: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert script.main(["--live"], Settings(_env_file=None, ai_provider="fake")) == 0
    out = capsys.readouterr().out
    assert "schema-valid: yes" in out and "retries:    0" in out and "grounded rules: 4 of 4" in out
    assert "latency:" in out and "first-try valid: yes" in out and no_network == []


def test_live_refuses_to_run_when_the_provider_is_not_configured(
    no_network: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert script.main(["--live"], Settings(_env_file=None, ai_provider="groq")) == 2
    assert "cannot run --live" in capsys.readouterr().out and no_network == []


def test_live_reports_a_provider_failure_with_exit_code_1_and_no_secrets(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Failing:
        provider, model = "groq", "some-model"

        def extract_requirement(self, **_: Any) -> Any:
            raise AIProviderError("The AI provider rate limit was reached.", details={"retries": 1})

    monkeypatch.setattr(script, "get_ai_provider", lambda *_: Failing())
    assert script.main(["--live"], groq_settings()) == 1
    out = capsys.readouterr().out
    assert "AI_PROVIDER_ERROR" in out and "rate limit" in out and KEY not in out


def test_live_with_a_mock_transport_groq_reports_retries_and_grounding(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from app.ai.groq_provider import GroqProvider
    from app.core.contracts import RQ014_EXTRACTION_EXAMPLE

    answers = iter(["{}", json.dumps(RQ014_EXTRACTION_EXAMPLE)])
    transport = httpx.MockTransport(lambda r: httpx.Response(
        200, json={"choices": [{"message": {"content": next(answers)}}]}))
    monkeypatch.setattr(script, "get_ai_provider", lambda s: GroqProvider(s, transport=transport))
    assert script.main(["--live"], groq_settings(ai_max_retries=1)) == 0
    out = capsys.readouterr().out
    assert "retries:    1" in out and "first-try valid: no" in out and "grounded rules:" in out and KEY not in out
