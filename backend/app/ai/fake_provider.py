"""Deterministic offline AI provider for development and tests.

It needs no network or API key and never pretends to be a language model:
results carry ``provider="fake"`` and the model name ``fake-deterministic-v1``.

``extract_requirement`` returns the RQ-014 sample extraction, adapted to the
attached policy texts (for example, the threshold in ``POL-OT-01@v2``). The
requirement text itself is ignored.

``suggest_edge_cases`` returns three scenarios. One of them carries a
deliberately wrong claimed expectation so the validator's AI-claim mismatch
path can be demonstrated offline.
"""

from __future__ import annotations

import copy
import re
import time
from collections.abc import Sequence
from typing import Any

from app.ai.schemas import AIResult, EdgeCaseSuggestion
from app.core.config import FAKE_MODEL_NAME
from app.core.contracts import (
    RQ014_EXTRACTION_EXAMPLE,
    AIProvider,
    AssertionTemplate,
    ExpectedResult,
    PolicyResponse,
    RequirementExtraction,
    RuleType,
    SpecResponse,
    TestInputs,
)

FAKE_PROMPT_VERSION = "fake-1.0"
DEFAULT_THRESHOLD = 480
_OT_SPAN = re.compile(r"paid minutes above (\d+) in a single shift are overtime")


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _threshold(spec: SpecResponse) -> int:
    """Return the overtime threshold from a spec, or the default."""
    for rule in spec.rules:
        if RuleType(rule.type) is RuleType.THRESHOLD:
            value = rule.params.get("threshold")
            if isinstance(value, int):
                return value
    return DEFAULT_THRESHOLD


class FakeProvider:
    """Offline provider satisfying the ``RequirementAI`` protocol."""

    provider: AIProvider = AIProvider.FAKE
    model: str | None = FAKE_MODEL_NAME

    def extract_requirement(
        self, *, requirement_text: str, policies: Sequence[PolicyResponse]
    ) -> AIResult[RequirementExtraction]:
        """Return the sample extraction adapted to the attached policies."""
        started = time.perf_counter()
        data: dict[str, Any] = copy.deepcopy(RQ014_EXTRACTION_EXAMPLE)
        rules = {rule["rule_key"]: rule for rule in data["rules"]}
        by_code = {policy.policy_code: policy for policy in policies}

        overtime = by_code.get("POL-OT-01")
        if overtime is not None:
            rules["OT_THRESHOLD"]["policy_ref"] = overtime.ref
            match = _OT_SPAN.search(overtime.rule_text)
            if match is not None:
                rules["OT_THRESHOLD"]["params"]["threshold"] = int(match.group(1))
                rules["OT_THRESHOLD"]["source_span"] = match.group(0)
        meal = by_code.get("POL-MEAL-02")
        if meal is not None:
            rules["MEAL_DEDUCTION"]["policy_ref"] = meal.ref
        shift = by_code.get("POL-DATE-03")
        if shift is not None:
            rules["SHIFT_SPAN"]["policy_ref"] = shift.ref

        extraction = RequirementExtraction.model_validate(data)
        return AIResult(
            data=extraction,
            provider=self.provider,
            model=self.model,
            prompt_version=FAKE_PROMPT_VERSION,
            valid_first_try=True,
            retries=0,
            latency_ms=_elapsed_ms(started),
        )

    def suggest_edge_cases(self, *, spec: SpecResponse) -> AIResult[list[EdgeCaseSuggestion]]:
        """Return three edge-case scenarios; the third has a deliberately wrong claim."""
        started = time.perf_counter()
        threshold = _threshold(spec)
        suggestions = [
            EdgeCaseSuggestion(
                title="Shift ending exactly at midnight",
                rationale="A shift that ends at 00:00 must still be attributed to one shift.",
                inputs=TestInputs(
                    start_time="16:00", end_time="00:00", overnight=True, meal_break_minutes=None
                ),
                assertion=AssertionTemplate.PAID_EQUALS,
                claimed_expected=ExpectedResult(paid_minutes=480),
                rule_keys=["SHIFT_SPAN"],
            ),
            EdgeCaseSuggestion(
                title="Full 24-hour overnight shift with a break",
                rationale="Start and end at the same time with the overnight flag means 24 hours.",
                inputs=TestInputs(
                    start_time="08:00", end_time="08:00", overnight=True, meal_break_minutes=60
                ),
                assertion=AssertionTemplate.OT_EQUALS,
                claimed_expected=ExpectedResult(overtime_minutes=max(0, 1380 - threshold)),
                rule_keys=["OT_THRESHOLD", "SHIFT_SPAN", "MEAL_DEDUCTION"],
            ),
            EdgeCaseSuggestion(
                title="Standard overnight shift with a 30-minute break",
                rationale="The reference overnight scenario from the requirement.",
                inputs=TestInputs(
                    start_time="22:00", end_time="07:00", overnight=True, meal_break_minutes=30
                ),
                assertion=AssertionTemplate.OT_EQUALS,
                # Deliberately off by one so the AI-claim mismatch check can be demonstrated.
                claimed_expected=ExpectedResult(overtime_minutes=max(0, 510 - threshold) + 1),
                rule_keys=["OT_THRESHOLD", "SHIFT_SPAN", "MEAL_DEDUCTION"],
            ),
        ]
        return AIResult(
            data=suggestions,
            provider=self.provider,
            model=self.model,
            prompt_version=FAKE_PROMPT_VERSION,
            valid_first_try=True,
            retries=0,
            latency_ms=_elapsed_ms(started),
        )
