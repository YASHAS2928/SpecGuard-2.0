"""Focused tests for the provider-independent AI layer."""

from __future__ import annotations

from app.ai.edge_cases import suggest_edge_cases
from app.ai.extractor import extract_requirement
from app.ai.fake_provider import FakeProvider
from app.core.contracts import RequirementExtraction


POLICIES = [
    {"ref": "POL-OT-01@v1", "rule_text": "Paid minutes above 480 in one shift are overtime."},
    {"ref": "POL-MEAL-02@v1", "rule_text": "Deduct an approved unpaid meal once from shift span."},
    {"ref": "POL-DATE-03@v1", "rule_text": "A valid midnight crossing remains one shift."},
]


def test_fake_provider_returns_shared_extraction_contract() -> None:
    result = extract_requirement(
        "For an overnight shift, deduct an unpaid meal and apply overtime above 480 paid minutes.",
        POLICIES,
        FakeProvider(),
    )

    assert isinstance(result.extraction, RequirementExtraction)
    assert result.provider == "fake"
    assert result.fallback_used is False
    assert result.prompt_version == "ext-1.0"
    assert result.extraction.rules[0].params.threshold == 480


def test_invalid_provider_output_retries_then_falls_back() -> None:
    class BrokenProvider:
        provider = "test"
        model = "broken"

        def complete(self, _prompt: str):
            from app.ai.adapter import Completion

            del _prompt
            return Completion("not-json", self.provider, self.model)

    result = extract_requirement("A valid overnight shift crosses midnight.", POLICIES, BrokenProvider())

    assert result.fallback_used is True
    assert result.retries == 2
    assert result.provider == "fake"


def test_edge_cases_do_not_include_expected_results() -> None:
    suggestions = suggest_edge_cases()

    assert len(suggestions) >= 5
    assert any(item.inputs["overnight"] is True for item in suggestions)
    assert any(item.inputs["meal_break_minutes"] == -1 for item in suggestions)
    assert all("expected" not in item.model_dump() for item in suggestions)
