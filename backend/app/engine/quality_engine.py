"""``QualityEngineImpl``: the single Quality Engine behind ``QualityEngine``.

It wraps Member 2's deterministic modules instead of duplicating them:

* ``oracle`` helpers (``calculate_span``, ``deduct_meal``) are reused; the *threshold* and the
  *meal minimum* now come from the approved specification (Member 2's ``calculate`` only
  accepts a 480-minute threshold). With threshold 480 and no minimum it agrees with
  ``oracle.calculate`` exactly (cross-checked in tests).
* ``validator.validate_cases`` validates every test (V01-V12) and is given this oracle.
* ``defect_clustering.cluster_failures`` groups observed failures.
* ``interface.check_spec`` grounds the specification.

Expected values are computed here only. AI suggestions contribute inputs and an optional
claim; a claim that differs from the oracle is reported as V08 and never stored as expected.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from app.ai.schemas import EdgeCaseSuggestion
from app.core.audit import sha256_hex
from app.core.contracts import (
    AssertionTemplate,
    IssueSeverity,
    PolicyResponse,
    RequirementExtraction,
    RuleChange,
    RuleChangeKind,
    TestOrigin,
    TestTechnique,
    ValidationCode,
    ValidationIssue,
)

from . import interface
from .defect_clustering import cluster_failures as member2_cluster_failures
from .oracle import DomainError, PayResult, calculate_span, deduct_meal
from .protocol import (
    SUPPORTED_RULE_KEY,
    CriterionDraft,
    DesignedTest,
    DesignResult,
    EngineRule,
    EngineSpec,
    ExistingTest,
    FailureCluster,
    FailureRecord,
    ImpactItem,
    Oracle,
)
from .validator import validate_cases

DEFAULT_THRESHOLD = 480
REQUIREMENT_SOURCE = interface.REQUIREMENT_SOURCE
_TERMINAL = {"REJECTED", "OBSOLETE"}
_TECHNIQUES = {
    "BOUNDARY": TestTechnique.BOUNDARY,
    "EQUIVALENCE": TestTechnique.PARTITION,
    "OVERNIGHT": TestTechnique.PARTITION,
    "DEDUCTION": TestTechnique.PARTITION,
    "DECISION_TABLE": TestTechnique.DECISION,
    "NEGATIVE": TestTechnique.NEGATIVE,
}
_BASE_RISK = {
    TestTechnique.BOUNDARY: 8, TestTechnique.DECISION: 6, TestTechnique.NEGATIVE: 4,
    TestTechnique.PARTITION: 5, TestTechnique.EDGE: 7,
}
_CODE_BY_PREFIX = {code.value[:3]: code for code in ValidationCode}


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def make_oracle(threshold: int, min_qualifying: int) -> Oracle:
    """Deterministic oracle for a specification's parameters."""

    def run(start_time: str, end_time: str, overnight: bool, meal_break_minutes: int) -> PayResult:
        span = calculate_span(start_time, end_time, overnight)
        deduct_meal(span, meal_break_minutes)  # validates type, sign and length of the break
        deducted = meal_break_minutes if meal_break_minutes >= min_qualifying else 0
        paid = span - deducted
        return PayResult(span, paid, max(0, paid - threshold))

    return run


def _contract_expected(oracle: Oracle, inputs: dict[str, Any], assertion: AssertionTemplate) -> dict[str, Any]:
    expected: dict[str, Any] = {"paid_minutes": None, "overtime_minutes": None, "rejects": False}
    try:
        result = oracle(**inputs)
    except (DomainError, TypeError):
        expected["rejects"] = True
        return expected
    if assertion is AssertionTemplate.PAID_EQUALS:
        expected["paid_minutes"] = result.paid_minutes
    elif assertion is AssertionTemplate.OT_EQUALS:
        expected["overtime_minutes"] = result.overtime_minutes
    else:  # a REJECTS test the oracle accepts: keep the real values so V07 can flag it
        expected["paid_minutes"], expected["overtime_minutes"] = result.paid_minutes, result.overtime_minutes
    return expected


def _internal_expected(oracle: Oracle, inputs: dict[str, Any]) -> dict[str, Any]:
    try:
        result = oracle(**inputs)
    except (DomainError, TypeError):
        return {"status_code": 422}
    return {"paid_minutes": result.paid_minutes, "overtime_minutes": result.overtime_minutes}


def _claim_for_validator(claim: dict[str, Any] | None, internal: dict[str, Any]) -> dict[str, Any] | None:
    """Express a partial AI claim in the validator's full form so only wrong fields mismatch."""
    if claim is None:
        return None
    if claim.get("rejects"):
        return {"status_code": 422}
    provided = {k: claim[k] for k in ("paid_minutes", "overtime_minutes") if claim.get(k) is not None}
    return {**internal, **provided} if "paid_minutes" in internal else provided


class QualityEngineImpl:
    """The one Quality Engine implementation."""

    # --- Specification -------------------------------------------------------------

    def to_engine_spec(
        self, *, rules: Sequence[EngineRule], requirement_code: str, requirement_text: str,
        policies: Sequence[PolicyResponse], today: date,
    ) -> EngineSpec:
        threshold, minimum = DEFAULT_THRESHOLD, 0
        for rule in rules:
            if rule.type == "THRESHOLD" and isinstance(rule.params.get("threshold"), int):
                threshold = rule.params["threshold"]
            if rule.type == "DEDUCTION" and isinstance(rule.params.get("min_qualifying"), int):
                minimum = rule.params["min_qualifying"]
        # An announced policy is valid to test for: evaluate on or after its start date.
        on_date = max([today, *(policy.effective_from for policy in policies)])
        return EngineSpec(requirement_code, requirement_text, tuple(rules), tuple(policies),
                          threshold, minimum, on_date)

    def check_spec(self, extraction: RequirementExtraction, requirement_text: str,
                   policies: Sequence[PolicyResponse]) -> list[ValidationIssue]:
        return interface.check_spec(extraction, requirement_text, policies)

    def oracle(self, spec: EngineSpec) -> Oracle:
        return make_oracle(spec.threshold, spec.min_qualifying)

    # --- Criteria -------------------------------------------------------------------

    def derive_criteria(self, spec: EngineSpec) -> list[CriterionDraft]:
        drafts: list[CriterionDraft] = []
        for index, rule in enumerate(spec.rules, start=1):
            code = f"AC-{index}"
            if rule.type == "THRESHOLD":
                t = rule.params.get("threshold")
                given, when = f"an approved shift with paid minutes above {t}", "overtime is calculated"
                then = f"overtime equals paid minutes minus {t}"
            elif rule.type == "DEDUCTION":
                m = rule.params.get("min_qualifying")
                given = f"a shift with a recorded unpaid meal break of {m} minutes or more"
                when, then = "paid minutes are calculated", "the recorded meal break is deducted once"
            elif rule.type == "SHIFT_SPAN":
                given = "a shift that crosses midnight with the overnight flag set"
                when, then = "the shift span is calculated", "the crossing counts as one shift"
            else:
                given = "a shift whose end time is earlier than its start time without the overnight flag"
                when, then = "the shift is submitted", "the request is rejected"
            drafts.append(CriterionDraft(code, rule.rule_key, given, when, then))
        return drafts

    # --- Test design ------------------------------------------------------------------

    def _designs(self, spec: EngineSpec) -> list[tuple[str, str, str, dict[str, Any], str, str]]:
        """(name, technique, partition, inputs, assertion, rationale)."""
        def inp(start: str, end: str, overnight: bool, meal: int) -> dict[str, Any]:
            return {"start_time": start, "end_time": end, "overnight": overnight, "meal_break_minutes": meal}

        t, start = spec.threshold, 8 * 60
        designs: list[tuple[str, str, str, dict[str, Any], str, str]] = []
        if 1 <= t - 1 and start + t + 1 < 1440 and t + 1 <= 960:
            for label, k, name in (("T-1", -1, "threshold_minus_one"), ("T", 0, "threshold_exact"),
                                   ("T+1", 1, "threshold_plus_one")):
                designs.append((name, "BOUNDARY", label, inp("08:00", _hhmm(start + t + k), False, 0),
                                "OT_EQUALS", f"Paid minutes = {t + k}: {['just below', 'exactly at', 'just above'][k + 1]} the {t}-minute threshold."))
        designs += [
            ("daytime_no_break", "EQUIVALENCE", "daytime", inp("09:00", "17:30", False, 0), "PAID_EQUALS",
             "Typical daytime shift without a meal break."),
            ("overnight_with_break", "OVERNIGHT", "overnight", inp("22:00", "07:00", True, 30), "PAID_EQUALS",
             "Overnight shift crossing midnight with a 30-minute meal break."),
            ("daytime_with_break", "DEDUCTION", "meal", inp("08:00", "17:00", False, 30), "PAID_EQUALS",
             "Daytime shift with one 30-minute meal deduction."),
            ("overnight_no_break", "DECISION_TABLE", "overnight_no_meal", inp("22:00", "06:00", True, 0), "PAID_EQUALS",
             "Overnight shift without a meal break."),
            ("overnight_overtime", "DECISION_TABLE", "overnight_overtime", inp("22:00", "07:00", True, 30), "OT_EQUALS",
             "Overnight overtime after the meal deduction."),
            ("negative_meal", "NEGATIVE", "invalid_meal", inp("09:00", "17:00", False, -1), "REJECTS",
             "A negative meal break is rejected."),
            ("meal_exceeds_span", "NEGATIVE", "invalid_meal", inp("09:00", "10:00", False, 61), "REJECTS",
             "A meal break longer than the shift is rejected."),
            ("missing_overnight", "NEGATIVE", "invalid_span", inp("22:00", "07:00", False, 30), "REJECTS",
             "An earlier end time without the overnight flag is rejected."),
            ("bad_time", "NEGATIVE", "invalid_time", inp("9am", "17:00", False, 0), "REJECTS",
             "A malformed time is rejected."),
            ("ambiguous_duration", "NEGATIVE", "invalid_span", inp("09:00", "09:00", False, 0), "REJECTS",
             "Equal start and end times are ambiguous and rejected."),
            ("excessive_duration", "NEGATIVE", "invalid_span", inp("04:00", "23:00", False, 0), "REJECTS",
             "A shift longer than 960 minutes is rejected."),
        ]
        return designs

    def _link_rules(self, spec: EngineSpec, assertion: AssertionTemplate, inputs: dict[str, Any],
                    partition: str) -> tuple[str, ...]:
        by_type: dict[str, str] = {}
        for rule in spec.rules:
            by_type.setdefault(rule.type, rule.rule_key)
        overnight = inputs.get("overnight") is True
        meal = inputs.get("meal_break_minutes")
        has_meal = isinstance(meal, int) and not isinstance(meal, bool) and meal > 0
        if assertion is AssertionTemplate.OT_EQUALS:
            order = ["THRESHOLD", "SHIFT_SPAN" if overnight else "", "DEDUCTION" if has_meal else ""]
        elif assertion is AssertionTemplate.PAID_EQUALS:
            order = ["SHIFT_SPAN" if overnight else "", "DEDUCTION" if has_meal else "", "SHIFT_SPAN"]
        else:
            order = ["DEDUCTION" if partition == "invalid_meal" else "", "VALIDATION", "SHIFT_SPAN"]
        keys: list[str] = []
        for rule_type in order:
            key = by_type.get(rule_type)
            if key and key not in keys:
                keys.append(key)
        return tuple(keys or [spec.rules[0].rule_key])

    def _spans(self, spec: EngineSpec, rule_keys: Sequence[str]) -> list[dict[str, Any]]:
        sources = {REQUIREMENT_SOURCE: spec.requirement_text,
                   **{policy.ref: policy.rule_text for policy in spec.policies}}
        by_key = {rule.rule_key: rule for rule in spec.rules}
        spans: list[dict[str, Any]] = []
        for key in rule_keys:
            rule = by_key[key]
            for source_id in (REQUIREMENT_SOURCE, rule.policy_ref):
                if source_id in sources:
                    located = interface.locate_span(rule.source_span, sources[source_id])
                    if located:
                        spans.append({"source_id": source_id, "start": located[0], "end": located[1],
                                      "text": sources[source_id][located[0]:located[1]]})
                        break
        return spans

    def design_tests(self, spec: EngineSpec, ai_suggestions: Sequence[EdgeCaseSuggestion] = ()) -> DesignResult:
        oracle = self.oracle(spec)
        criteria = {draft.rule_key: draft.code for draft in self.derive_criteria(spec)}
        drafts: list[DesignedTest] = []
        unsupported: set[str] = set()

        def add(origin: TestOrigin, technique: TestTechnique, partition: str, inputs: dict[str, Any],
                assertion: AssertionTemplate, rationale: str, rule_keys: tuple[str, ...],
                claim: dict[str, Any] | None = None, is_unsupported: bool = False) -> None:
            fixture_hash = sha256_hex({"inputs": inputs, "assertion": assertion.value}) or ""
            key = f"{len(drafts) + 1:03d}-{fixture_hash[:12]}"
            if is_unsupported:
                unsupported.add(key)
            risk = _BASE_RISK[technique] + (2 if inputs.get("overnight") is True else 0)
            drafts.append(DesignedTest(
                key=key, fixture_hash=fixture_hash, origin=origin, technique=technique, partition=partition,
                inputs=inputs, assertion=assertion, expected=_contract_expected(oracle, inputs, assertion),
                ai_claimed_expected=claim, rationale=rationale[:500], rule_keys=rule_keys,
                criterion_codes=tuple(dict.fromkeys(criteria[k] for k in rule_keys)), risk_score=min(risk, 20)))

        for _name, technique, partition, inputs, assertion_name, rationale in self._designs(spec):
            assertion = AssertionTemplate(assertion_name)
            add(TestOrigin.ENGINE, _TECHNIQUES[technique], partition, inputs, assertion, rationale,
                self._link_rules(spec, assertion, inputs, partition))

        known = set(spec.rule_keys())
        for suggestion in ai_suggestions:
            inputs = suggestion.inputs.model_dump()
            if inputs["meal_break_minutes"] is None:
                inputs["meal_break_minutes"] = 0  # an absent break means zero minutes
            claimed = suggestion.claimed_expected.model_dump() if suggestion.claimed_expected else None
            linked = tuple(k for k in suggestion.rule_keys if k in known)
            bad = not suggestion.rule_keys or len(linked) != len(suggestion.rule_keys)
            add(TestOrigin.AI, TestTechnique.EDGE, "ai_edge", inputs, suggestion.assertion,
                f"{suggestion.title}: {suggestion.rationale}",
                linked or (spec.rules[0].rule_key,), claimed, is_unsupported=bad)

        issues, plan_issues = self._validate(spec, drafts, unsupported)
        tests = tuple(
            DesignedTest(**{**draft.__dict__, "issues": tuple(issues.get(draft.key, ()))}) for draft in drafts
        )
        return DesignResult(tests, tuple(plan_issues))

    # --- Validation (Member 2's validate_cases) -----------------------------------------------

    def _validate(self, spec: EngineSpec, drafts: Sequence[DesignedTest],
                  unsupported: set[str]) -> tuple[dict[str, list[ValidationIssue]], list[ValidationIssue]]:
        oracle = self.oracle(spec)
        criteria = self.derive_criteria(spec)
        policy_registry = {
            policy.policy_code: {"effective_from": policy.effective_from.isoformat(),
                                 "effective_to": policy.effective_to.isoformat() if policy.effective_to else None}
            for policy in spec.policies
        }
        sources = {REQUIREMENT_SOURCE: spec.requirement_text,
                   **{policy.ref: policy.rule_text for policy in spec.policies}}
        code = spec.requirement_code
        cases: list[dict[str, Any]] = []
        for draft in drafts:
            internal = _internal_expected(oracle, draft.inputs)
            cases.append({
                "id": draft.key, "version": 1, "requirement_id": code,
                "criterion_id": draft.criterion_codes[0] if draft.criterion_codes else None,
                "policy_ids": [policy.policy_code for policy in spec.policies],
                "rule_key": f"UNSUPPORTED:{draft.rule_keys[0]}" if draft.key in unsupported else SUPPORTED_RULE_KEY,
                "technique": draft.technique.value, "partition": draft.partition, "inputs": dict(draft.inputs),
                "rationale": draft.rationale,  # scanned by the validator for instruction-like text (V11)
                "assertion_type": draft.assertion.value, "expected": internal,
                "ai_claimed_expected": _claim_for_validator(draft.ai_claimed_expected, internal),
                "source_spans": self._spans(spec, draft.rule_keys),
                "validation_state": "DRAFT", "approval_state": "PENDING",
            })
        found = validate_cases(
            cases, requirements={code: {}}, criteria={c.code: {"requirement_id": code} for c in criteria},
            policies=policy_registry, sources=sources, on_date=spec.on_date, oracle=oracle,
        )
        per_test: dict[str, list[ValidationIssue]] = {}
        plan: list[ValidationIssue] = []
        for item in found:
            issue = ValidationIssue(
                code=_CODE_BY_PREFIX[item["code"]],
                severity=IssueSeverity.WARN if item["severity"] == "WARNING" else IssueSeverity.BLOCK,
                message=str(item["message"])[:500], detail=item.get("details") or None,
            )
            if item.get("test_id") is None:
                plan.append(issue)
            else:
                per_test.setdefault(item["test_id"], []).append(issue)
        return per_test, plan

    # --- Change impact ------------------------------------------------------------------------

    def classify_rules(self, old: EngineSpec, new: EngineSpec) -> list[RuleChange]:
        before = {rule.rule_key: rule for rule in old.rules}
        after = {rule.rule_key: rule for rule in new.rules}
        changes: list[RuleChange] = []
        for key in sorted(before.keys() | after.keys()):
            if key not in before:
                changes.append(RuleChange(rule_key=key, kind=RuleChangeKind.ADDED, after=dict(after[key].params)))
            elif key not in after:
                changes.append(RuleChange(rule_key=key, kind=RuleChangeKind.REMOVED, before=dict(before[key].params)))
            else:
                old_rule, new_rule = before[key], after[key]
                fields = sorted(f for f in old_rule.params.keys() | new_rule.params.keys()
                                if old_rule.params.get(f) != new_rule.params.get(f))
                if fields:
                    changes.append(RuleChange(
                        rule_key=key, kind=RuleChangeKind.PARAM_CHANGED,
                        before={f: old_rule.params.get(f) for f in fields},
                        after={f: new_rule.params.get(f) for f in fields}, changed_fields=fields))
                if old_rule.policy_ref != new_rule.policy_ref:
                    changes.append(RuleChange(
                        rule_key=key, kind=RuleChangeKind.POLICY_VERSION_CHANGED,
                        before={"policy_ref": old_rule.policy_ref}, after={"policy_ref": new_rule.policy_ref},
                        changed_fields=["policy_ref"]))
        return changes

    def classify_tests(self, old_tests: Sequence[ExistingTest], new_tests: Sequence[ExistingTest]) -> list[ImpactItem]:
        new_by_hash = {test.fixture_hash: test for test in new_tests}
        old_hashes = {test.fixture_hash for test in old_tests if test.status not in _TERMINAL}
        items: list[ImpactItem] = []
        for old in old_tests:
            if old.status in _TERMINAL:
                continue
            match = new_by_hash.get(old.fixture_hash)
            if match is None:
                reason = ("The AI edge case has no runnable counterpart on the new specification."
                          if old.origin == "AI" else "The scenario is no longer part of the designed test set.")
                items.append(ImpactItem("OBSOLETE", reason, old.id, None, old.expected, None))
            elif match.expected != old.expected:
                items.append(ImpactItem("STALE_EXPECTED", "The expected result changes under the new specification.",
                                        old.id, match.id, old.expected, match.expected))
            else:
                items.append(ImpactItem("UNAFFECTED", "Same scenario and expected result.",
                                        old.id, match.id, old.expected, match.expected))
        for new in new_tests:
            if new.fixture_hash not in old_hashes:
                items.append(ImpactItem("NEW", "New scenario for the changed specification.", None, new.id, None, new.expected))
        return items

    # --- Defect clustering ---------------------------------------------------------------------------

    def cluster_failures(self, failures: Sequence[FailureRecord]) -> list[FailureCluster]:
        results = [{"test_id": f.test_id, "status": "FAIL"} for f in failures]
        cases = [{"id": f.test_id, "rule_key": f.rule_key, "partition": f"overnight={str(f.overnight).lower()}",
                  "technique": f.assertion} for f in failures]
        by_test = {f.test_id: f for f in failures}
        clusters: list[FailureCluster] = []
        for cluster in member2_cluster_failures(results, cases):
            members = [by_test[test_id] for test_id in cluster["test_ids"]]
            key = f"{cluster['rule_key']}|{cluster['partition']}|{cluster['technique']}"
            clusters.append(FailureCluster(
                cluster_key=key,
                title=f"{cluster['rule_key']} fails whenever {cluster['partition']} ({cluster['technique']})",
                rule_key=cluster["rule_key"],
                partition={"overnight": members[0].overnight, "assertion": cluster["technique"]},
                result_ids=tuple(m.result_id for m in members), test_ids=tuple(cluster["test_ids"])))
        return clusters
