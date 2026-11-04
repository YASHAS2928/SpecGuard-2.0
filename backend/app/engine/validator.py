"""Fail-closed deterministic validation. Issue dicts are proposed adapter data."""

from datetime import date
import json
import re
from .grounding import grounded
from .oracle import DomainError, calculate

SEVERITY = {f"V{i:02d}": "BLOCK" for i in range(1, 13)}
SEVERITY["V11"] = "WARNING"
REQUIRED_PARTITIONS = {"T-1", "T", "T+1", "overnight", "invalid_meal", "invalid_span", "invalid_time"}
ASSERTIONS = {"PAID_EQUALS", "OT_EQUALS", "REJECTS"}
INPUTS = {"start_time", "end_time", "overnight", "meal_break_minutes"}
REQUIRED_POLICIES = {"POL-OT-01", "POL-MEAL-02", "POL-DATE-03"}
SUSPECT = re.compile(r"ignore (?:all |previous )?instructions|mark everything pass|\beval\s*\(|\bexec\s*\(", re.I)
TARGET = "http://127.0.0.1:9000/v1/pay/calculate"


def _issue(code: str, message: str, test_id: str | None = None, **details) -> dict:
    return {"code": code, "severity": SEVERITY[code], "message": message,
            "test_id": test_id, "details": details}


def validate_cases(cases: list[dict], *, requirements: dict, criteria: dict,
                   policies: dict, sources: dict[str, str] | None,
                   on_date: date, target: str = TARGET,
                   required_partitions: set[str] | None = None,
                   oracle=calculate) -> list[dict]:
    """Caller supplies authoritative registries; missing registries fail closed.

    ``oracle`` recomputes expected values (default: the 480-minute-threshold oracle).
    """
    issues, signatures, covered = [], set(), set()
    if not isinstance(cases, list):
        return [_issue("V01", "cases must be a list")]
    for case in cases:
        if not isinstance(case, dict):
            issues.append(_issue("V01", "case must be an object"))
            continue
        test_id = case.get("id")
        required = {"id", "version", "requirement_id", "policy_ids", "rule_key", "technique",
                    "partition", "inputs", "assertion_type", "expected"}
        if (not required <= case.keys() or not isinstance(test_id, str) or not test_id
                or type(case.get("version")) is not int or case["version"] < 1
                or not isinstance(case.get("inputs"), dict)
                or set(case["inputs"]) != INPUTS
                or not all(isinstance(key, str) for key in case)
                or not isinstance(case.get("policy_ids"), list)
                or not all(isinstance(x, str) for x in case["policy_ids"])
                or not isinstance(case.get("requirement_id"), str)
                or not isinstance(case.get("rule_key"), str)
                or not isinstance(case.get("technique"), str)
                or not isinstance(case.get("partition"), str)
                or case.get("criterion_id") is not None and not isinstance(case.get("criterion_id"), str)
                or case.get("source_spans") is not None and not isinstance(case.get("source_spans"), list)
                or case.get("assertion_type") not in ASSERTIONS
                or not isinstance(case.get("expected"), dict)):
            issues.append(_issue("V01", "case shape or assertion is invalid", test_id))
            continue
        if sources is None or not case.get("source_spans") or not all(
                grounded(span, sources) for span in case["source_spans"]):
            issues.append(_issue("V02", "source span missing or unverified", test_id))
        for missing_policy in sorted(REQUIRED_POLICIES - set(case["policy_ids"])):
            issues.append(_issue("V03", "required policy missing", test_id, policy_id=missing_policy))
        for policy_id in case.get("policy_ids", []):
            policy = policies.get(policy_id) if isinstance(policies, dict) else None
            if policy is None:
                issues.append(_issue("V03", "unknown policy", test_id, policy_id=policy_id))
            else:
                try:
                    first = date.fromisoformat(policy["effective_from"])
                    last = date.fromisoformat(policy["effective_to"]) if policy.get("effective_to") else None
                    if on_date < first or (last and on_date > last):
                        issues.append(_issue("V04", "policy not effective", test_id, policy_id=policy_id))
                except (KeyError, TypeError, ValueError):
                    issues.append(_issue("V04", "policy effective dates unavailable", test_id, policy_id=policy_id))
        if case["rule_key"] != "RQ-014:TIME_TO_PAY":
            issues.append(_issue("V05", "unsupported rule", test_id))
        requirement_id, criterion_id = case.get("requirement_id"), case.get("criterion_id")
        if (not isinstance(requirements, dict) or requirement_id not in requirements
                or (criterion_id is not None and
                    (not isinstance(criteria, dict) or criterion_id not in criteria
                     or not isinstance(criteria[criterion_id], dict)
                     or criteria[criterion_id].get("requirement_id") != requirement_id))):
            issues.append(_issue("V06", "broken requirement or criterion reference", test_id))
        try:
            result = oracle(**case["inputs"])
            oracle_expected = {"paid_minutes": result.paid_minutes,
                               "overtime_minutes": result.overtime_minutes}
            if case["assertion_type"] == "REJECTS":
                issues.append(_issue("V07", "REJECTS case is valid to oracle", test_id))
        except (DomainError, TypeError) as error:
            if case["assertion_type"] != "REJECTS":
                issues.append(_issue("V07", "oracle cannot calculate case", test_id, error=str(error)))
            oracle_expected = {"status_code": 422}
        if case["expected"] != oracle_expected:
            issues.append(_issue("V07", "stored expected differs from oracle", test_id,
                                 oracle_expected=oracle_expected))
        claim = case.get("ai_claimed_expected")
        if claim is not None and claim != oracle_expected:
            issues.append(_issue("V08", "AI claim differs from oracle", test_id,
                                 oracle_expected=oracle_expected))
        signature = (json.dumps(case["inputs"], sort_keys=True), case["assertion_type"])
        if signature in signatures:
            issues.append(_issue("V09", "semantic duplicate", test_id))
        signatures.add(signature)
        covered.add(case["partition"])
        if SUSPECT.search(json.dumps(case, default=str)):
            issues.append(_issue("V11", "instruction-like content requires review", test_id))
        if target != TARGET or (case.get("target") is not None and case["target"] != TARGET):
            issues.append(_issue("V12", "forbidden execution target", test_id))
    missing = (REQUIRED_PARTITIONS if required_partitions is None else required_partitions) - covered
    if missing:
        issues.append(_issue("V10", "required coverage partitions missing", missing=sorted(missing)))
    return issues
