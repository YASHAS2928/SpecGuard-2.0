"""The Quality Engine boundary used by the backend (one implementation behind one protocol).

The backend talks only to ``QualityEngine``. ``QualityEngineImpl`` (``quality_engine.py``)
wraps Member 2's deterministic functions. Expected values are produced here by a
deterministic oracle; the AI and the API layer never set them.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from app.ai.schemas import EdgeCaseSuggestion
from app.core.contracts import (
    AssertionTemplate,
    PolicyResponse,
    RequirementExtraction,
    RuleChange,
    TestOrigin,
    TestTechnique,
    ValidationIssue,
)

# Rule key every engine fixture is traced to by Member 2's validator (V05).
SUPPORTED_RULE_KEY = "RQ-014:TIME_TO_PAY"


@dataclass(frozen=True)
class EngineRule:
    rule_key: str
    type: str
    params: dict[str, Any]
    policy_ref: str | None
    source_span: str


@dataclass(frozen=True)
class EngineSpec:
    """The approved specification, reduced to what the engine needs."""

    requirement_code: str
    requirement_text: str
    rules: tuple[EngineRule, ...]
    policies: tuple[PolicyResponse, ...]
    threshold: int
    min_qualifying: int
    on_date: date

    def rule_keys(self) -> list[str]:
        return [rule.rule_key for rule in self.rules]


@dataclass(frozen=True)
class CriterionDraft:
    code: str
    rule_key: str
    given: str
    when: str
    then: str


@dataclass(frozen=True)
class DesignedTest:
    """A test the engine designed. ``expected`` is oracle-computed (contract form)."""

    key: str
    fixture_hash: str
    origin: TestOrigin
    technique: TestTechnique
    partition: str
    inputs: dict[str, Any]
    assertion: AssertionTemplate
    expected: dict[str, Any]
    ai_claimed_expected: dict[str, Any] | None
    rationale: str
    rule_keys: tuple[str, ...]  # the first entry is the primary rule
    criterion_codes: tuple[str, ...]
    risk_score: int
    issues: tuple[ValidationIssue, ...] = field(default=())


@dataclass(frozen=True)
class DesignResult:
    """Designed tests plus plan-level findings (for example a V10 coverage gap)."""

    tests: tuple[DesignedTest, ...]
    plan_issues: tuple[ValidationIssue, ...] = field(default=())


@dataclass(frozen=True)
class ExistingTest:
    """A persisted test, as seen by impact classification."""

    id: str
    tc_code: str
    fixture_hash: str
    expected: dict[str, Any]
    status: str
    origin: str = "ENGINE"


@dataclass(frozen=True)
class ImpactItem:
    impact_class: str  # STALE_EXPECTED | OBSOLETE | NEW | UNAFFECTED
    reason: str
    old_id: str | None
    new_key: str | None
    old_expected: dict[str, Any] | None
    new_expected: dict[str, Any] | None


@dataclass(frozen=True)
class FailureRecord:
    result_id: str
    test_id: str
    rule_key: str
    overnight: bool
    assertion: str


@dataclass(frozen=True)
class FailureCluster:
    cluster_key: str
    title: str
    rule_key: str
    partition: dict[str, Any]
    result_ids: tuple[str, ...]
    test_ids: tuple[str, ...]


Oracle = Callable[..., Any]


class QualityEngine(Protocol):
    """Everything the backend needs from the Quality Engine."""

    def to_engine_spec(
        self,
        *,
        rules: Sequence[EngineRule],
        requirement_code: str,
        requirement_text: str,
        policies: Sequence[PolicyResponse],
        today: date,
    ) -> EngineSpec: ...

    def check_spec(
        self, extraction: RequirementExtraction, requirement_text: str, policies: Sequence[PolicyResponse]
    ) -> list[ValidationIssue]: ...

    def oracle(self, spec: EngineSpec) -> Oracle:
        """Return ``f(**inputs) -> PayResult`` raising ``DomainError`` for invalid inputs."""

    def derive_criteria(self, spec: EngineSpec) -> list[CriterionDraft]: ...

    def design_tests(
        self, spec: EngineSpec, ai_suggestions: Sequence[EdgeCaseSuggestion] = ()
    ) -> DesignResult:
        """Engine tests (oracle expected values) plus validated AI edge cases; every test validated."""

    def classify_rules(self, old: EngineSpec, new: EngineSpec) -> list[RuleChange]: ...

    def classify_tests(
        self, old_tests: Sequence[ExistingTest], new_tests: Sequence[ExistingTest]
    ) -> list[ImpactItem]: ...

    def cluster_failures(self, failures: Sequence[FailureRecord]) -> list[FailureCluster]: ...
