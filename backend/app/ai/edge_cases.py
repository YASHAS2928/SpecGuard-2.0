"""AI-layer edge-case suggestions; expected values remain oracle-owned."""

from __future__ import annotations

from typing import Any, Literal

from app.core.contracts import ContractModel, RuleKey, ShortAIText, TestInputs


class EdgeCaseSuggestion(ContractModel):
    """An input suggestion that the deterministic engine must evaluate later."""

    name: ShortAIText
    technique: Literal["BOUNDARY", "NEGATIVE", "EDGE", "DECISION"]
    rule_key: RuleKey
    inputs: dict[str, Any]
    rationale: ShortAIText


def suggest_edge_cases() -> list[EdgeCaseSuggestion]:
    """Return safe, deterministic suggestions for the RQ-014 demonstration domain."""
    return [
        EdgeCaseSuggestion(
            name="exact overtime threshold",
            technique="BOUNDARY",
            rule_key="OT_THRESHOLD",
            inputs=TestInputs(start_time="08:00", end_time="16:00", overnight=False, meal_break_minutes=0).model_dump(),
            rationale="Checks the exact 480 paid-minute boundary.",
        ),
        EdgeCaseSuggestion(
            name="one minute above threshold",
            technique="BOUNDARY",
            rule_key="OT_THRESHOLD",
            inputs=TestInputs(start_time="08:00", end_time="16:01", overnight=False, meal_break_minutes=0).model_dump(),
            rationale="Checks the first minute above the threshold.",
        ),
        EdgeCaseSuggestion(
            name="overnight shift with meal",
            technique="EDGE",
            rule_key="SHIFT_SPAN",
            inputs=TestInputs(start_time="22:00", end_time="07:00", overnight=True, meal_break_minutes=30).model_dump(),
            rationale="Checks midnight crossing and one meal deduction together.",
        ),
        EdgeCaseSuggestion(
            name="negative meal break",
            technique="NEGATIVE",
            rule_key="VALIDATE_MEAL",
            inputs={"start_time": "09:00", "end_time": "17:00", "overnight": False, "meal_break_minutes": -1},
            rationale="Checks rejection of a negative break value.",
        ),
        EdgeCaseSuggestion(
            name="missing overnight flag",
            technique="NEGATIVE",
            rule_key="END_BEFORE_START",
            inputs=TestInputs(start_time="22:00", end_time="07:00", overnight=False, meal_break_minutes=0).model_dump(),
            rationale="Checks rejection when an earlier end lacks overnight=true.",
        ),
    ]
