"""Fake provider and provider factory tests."""

from __future__ import annotations

import importlib
import uuid
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from app.ai.adapter import get_ai_provider
from app.ai.fake_provider import FakeProvider
from app.ai.integration_interface import RequirementAI
from app.core.config import FAKE_MODEL_NAME, Settings
from app.core.contracts import AIProvider, PolicyResponse, RequirementExtraction, RuleType
from app.core.errors import AIProviderNotConfiguredError
from app.database.seed import FICTIONAL_POLICIES
from app.services.integration_service import get_spec_checker


def make_policies(*refs: str) -> list[PolicyResponse]:
    wanted = set(refs)
    return [
        PolicyResponse(
            id=uuid.uuid4(),
            policy_code=seed.policy_code,
            version=seed.version,
            ref=f"{seed.policy_code}@v{seed.version}",
            title=seed.title,
            rule_text=seed.rule_text,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            fictional=True,
        )
        for seed in FICTIONAL_POLICIES
        if f"{seed.policy_code}@v{seed.version}" in wanted
    ]


V1 = ("POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1")
V2 = ("POL-OT-01@v2", "POL-MEAL-02@v1", "POL-DATE-03@v1")


def patch_import(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, Any]) -> None:
    real_import = importlib.import_module

    def fake_import(name: str, package: str | None = None) -> Any:
        if name in mapping:
            value = mapping[name]
            if isinstance(value, Exception):
                raise value
            return value
        return real_import(name, package)

    monkeypatch.setattr("app.ai.adapter.importlib.import_module", fake_import)


# --- Fake provider ---------------------------------------------------------------


def test_fake_extraction_is_valid_and_labelled_fake() -> None:
    result = FakeProvider().extract_requirement(requirement_text="x" * 20, policies=make_policies(*V1))
    assert isinstance(result.data, RequirementExtraction)
    assert result.provider is AIProvider.FAKE
    assert result.model == FAKE_MODEL_NAME
    assert result.valid_first_try is True and result.retries == 0
    threshold_rule = next(r for r in result.data.rules if r.type == "THRESHOLD")
    assert threshold_rule.params.threshold == 480
    assert threshold_rule.policy_ref == "POL-OT-01@v1"


def test_fake_extraction_follows_the_attached_policy_version() -> None:
    result = FakeProvider().extract_requirement(requirement_text="x" * 20, policies=make_policies(*V2))
    threshold_rule = next(r for r in result.data.rules if r.type == "THRESHOLD")
    assert threshold_rule.params.threshold == 450
    assert threshold_rule.policy_ref == "POL-OT-01@v2"
    assert threshold_rule.source_span == "paid minutes above 450 in a single shift are overtime"


def test_fake_extraction_is_deterministic() -> None:
    provider = FakeProvider()
    first = provider.extract_requirement(requirement_text="x" * 20, policies=make_policies(*V1))
    second = provider.extract_requirement(requirement_text="x" * 20, policies=make_policies(*V1))
    assert first.data.model_dump(mode="json") == second.data.model_dump(mode="json")


def test_fake_edge_cases_include_one_deliberately_wrong_claim() -> None:
    spec: Any = SimpleNamespace(
        rules=[SimpleNamespace(type=RuleType.THRESHOLD, params={"threshold": 480})]
    )
    result = FakeProvider().suggest_edge_cases(spec=spec)
    assert len(result.data) == 3
    assert len({item.title for item in result.data}) == 3
    wrong = [
        item
        for item in result.data
        if item.claimed_expected is not None and item.claimed_expected.overtime_minutes == 31
    ]
    assert len(wrong) == 1  # the correct value for 22:00-07:00 with a 30-minute break is 30


# --- Provider factory ----------------------------------------------------------------


def test_factory_returns_fake_provider() -> None:
    provider = get_ai_provider(Settings(_env_file=None, ai_provider="fake"))
    assert isinstance(provider, FakeProvider)
    assert isinstance(provider, RequirementAI)


def test_factory_reports_missing_groq_configuration() -> None:
    with pytest.raises(AIProviderNotConfiguredError) as caught:
        get_ai_provider(Settings(_env_file=None, ai_provider="groq"))
    issues = caught.value.details["issues"]
    assert any("GROQ_API_KEY" in issue for issue in issues)


def test_factory_reports_provider_module_not_delivered(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_import(
        monkeypatch,
        {"app.ai.groq_provider": ModuleNotFoundError("missing", name="app.ai.groq_provider")},
    )
    settings = Settings(_env_file=None, ai_provider="groq", groq_api_key="placeholder", groq_model="m")
    with pytest.raises(AIProviderNotConfiguredError) as caught:
        get_ai_provider(settings)
    assert "not implemented in this build" in caught.value.message


def test_factory_reports_missing_sdk_package(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_import(
        monkeypatch,
        {"app.ai.groq_provider": ModuleNotFoundError("No module named 'groq'", name="groq")},
    )
    settings = Settings(
        _env_file=None, ai_provider="groq", groq_api_key="placeholder", groq_model="m"
    )
    with pytest.raises(AIProviderNotConfiguredError) as caught:
        get_ai_provider(settings)
    assert "pip install groq" in caught.value.message


def test_factory_rejects_a_class_that_does_not_implement_the_interface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class GroqProvider:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

    patch_import(monkeypatch, {"app.ai.groq_provider": SimpleNamespace(GroqProvider=GroqProvider)})
    settings = Settings(_env_file=None, ai_provider="groq", groq_api_key="placeholder", groq_model="m")
    with pytest.raises(AIProviderNotConfiguredError) as caught:
        get_ai_provider(settings)
    assert "RequirementAI" in caught.value.message


def test_factory_builds_a_conforming_provider_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class GroqProvider(FakeProvider):
        def __init__(self, settings: Settings) -> None:
            self.provider = AIProvider.GROQ
            self.model = settings.groq_model

    patch_import(monkeypatch, {"app.ai.groq_provider": SimpleNamespace(GroqProvider=GroqProvider)})
    settings = Settings(
        _env_file=None, ai_provider="groq", groq_api_key="placeholder", groq_model="example-model"
    )
    provider = get_ai_provider(settings)
    assert provider.provider is AIProvider.GROQ
    assert provider.model == "example-model"


def test_missing_checker_interface_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_import(
        monkeypatch,
        {"app.engine.interface": ModuleNotFoundError("missing", name="app.engine.interface")},
    )
    assert get_spec_checker() is None


def test_checker_dependency_import_error_is_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_import(
        monkeypatch,
        {"app.engine.interface": ModuleNotFoundError("missing", name="checker_dependency")},
    )
    with pytest.raises(ModuleNotFoundError, match="missing"):
        get_spec_checker()


def test_checker_interface_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    def checker(*args: Any) -> list[Any]:
        return []

    patch_import(monkeypatch, {"app.engine.interface": SimpleNamespace(check_spec=checker)})
    assert get_spec_checker() is checker
