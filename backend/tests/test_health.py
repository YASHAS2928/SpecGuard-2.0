"""Tests for system endpoints and configuration behaviour."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import API_VERSION, APP_VERSION, BACKEND_DIR, FAKE_MODEL_NAME, Settings

# --- Endpoints -----------------------------------------------------------------

def test_health_returns_ok_with_fake_provider(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["environment"] == "test"
    assert body["ai"] == {
        "provider": "fake",
        "model": FAKE_MODEL_NAME,
        "configured": True,
        "issues": [],
    }

def test_version_endpoint(client: TestClient) -> None:
    response = client.get("/version")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "SpecGuard 2.0"
    assert body["version"] == APP_VERSION
    assert body["api_version"] == API_VERSION
    assert body["ai_provider"] == "fake"
    assert body["ai_model"] == FAKE_MODEL_NAME

def test_trace_id_generated_when_missing(client: TestClient) -> None:
    response = client.get("/health")
    trace_id = response.headers.get("X-Trace-ID")
    assert trace_id is not None
    assert re.fullmatch(r"[0-9a-f]{32}", trace_id)

def test_trace_id_echoed_when_safe(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Trace-ID": "demo-trace-001"})
    assert response.headers["X-Trace-ID"] == "demo-trace-001"

def test_unsafe_trace_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Trace-ID": "bad id <script>"})
    assert response.headers["X-Trace-ID"] != "bad id <script>"
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Trace-ID"])

def test_openapi_schema_lists_system_endpoints(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "SpecGuard 2.0"
    assert "/health" in schema["paths"]
    assert "/version" in schema["paths"]

# --- Configuration -------------------------------------------------------------

def test_groq_selected_without_key_reports_clear_issue() -> None:
    settings = Settings(_env_file=None, ai_provider="groq", groq_api_key=None, groq_model=None)
    issues = settings.ai_configuration_issues()
    assert not settings.is_ai_configured
    assert any("GROQ_API_KEY" in issue and "console.groq.com/keys" in issue for issue in issues)
    assert any("GROQ_MODEL" in issue for issue in issues)

def test_gemini_selected_without_key_reports_clear_issue() -> None:
    settings = Settings(
        _env_file=None, ai_provider="gemini", gemini_api_key=None, gemini_model=None
    )
    issues = settings.ai_configuration_issues()
    assert not settings.is_ai_configured
    assert any(
        "GEMINI_API_KEY" in issue and "aistudio.google.com/apikey" in issue for issue in issues
    )
    assert any("GEMINI_MODEL" in issue for issue in issues)

def test_fake_provider_needs_no_credentials() -> None:
    settings = Settings(_env_file=None, ai_provider="fake")
    assert settings.is_ai_configured
    assert settings.active_ai_model == FAKE_MODEL_NAME

def test_invalid_provider_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_provider="openai")

def test_blank_values_become_none() -> None:
    settings = Settings(_env_file=None, ai_provider="groq", groq_api_key="   ", groq_model="")
    assert settings.groq_api_key is None
    assert settings.groq_model is None

def test_relative_sqlite_path_resolves_to_backend_dir() -> None:
    settings = Settings(_env_file=None, database_url="sqlite:///./specguard.db")
    expected = f"sqlite:///{(BACKEND_DIR / 'specguard.db').resolve().as_posix()}"
    assert settings.resolved_database_url == expected

def test_non_sqlite_database_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="postgresql://localhost/specguard")

def test_secrets_are_masked() -> None:
    placeholder = "placeholder-not-a-real-key"
    settings = Settings(
        _env_file=None, ai_provider="groq", groq_api_key=placeholder, groq_model="any-model"
    )
    assert placeholder not in repr(settings)
    assert placeholder not in str(settings.model_dump())
    assert settings.groq_api_key is not None
    assert settings.groq_api_key.get_secret_value() == placeholder
    assert settings.is_ai_configured
