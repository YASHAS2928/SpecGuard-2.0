"""Deterministic draft cases; dicts are internal until Member 1 freezes contracts."""

from .oracle import DomainError, calculate

RULE_KEY = "RQ-014:TIME_TO_PAY"
POLICIES = ["POL-OT-01", "POL-MEAL-02", "POL-DATE-03"]

_DESIGNS = [
    ("threshold_minus_one", "BOUNDARY", "T-1", "08:00", "15:59", False, 0, "OT_EQUALS"),
    ("threshold_exact", "BOUNDARY", "T", "08:00", "16:00", False, 0, "OT_EQUALS"),
    ("threshold_plus_one", "BOUNDARY", "T+1", "08:00", "16:01", False, 0, "OT_EQUALS"),
    ("daytime_no_break", "EQUIVALENCE", "daytime", "09:00", "17:30", False, 0, "PAID_EQUALS"),
    ("overnight_with_break", "OVERNIGHT", "overnight", "22:00", "07:00", True, 30, "PAID_EQUALS"),
    ("daytime_with_break", "DEDUCTION", "meal", "08:00", "17:00", False, 30, "PAID_EQUALS"),
    ("overnight_no_break", "DECISION_TABLE", "overnight_no_meal", "22:00", "06:00", True, 0, "PAID_EQUALS"),
    ("negative_meal", "NEGATIVE", "invalid_meal", "09:00", "17:00", False, -1, "REJECTS"),
    ("meal_exceeds_span", "NEGATIVE", "invalid_meal", "09:00", "10:00", False, 61, "REJECTS"),
    ("missing_overnight", "NEGATIVE", "invalid_span", "22:00", "07:00", False, 30, "REJECTS"),
    ("bad_time", "NEGATIVE", "invalid_time", "9am", "17:00", False, 0, "REJECTS"),
    ("ambiguous_duration", "NEGATIVE", "invalid_span", "09:00", "09:00", False, 0, "REJECTS"),
    ("excessive_duration", "NEGATIVE", "invalid_span", "04:00", "23:00", False, 0, "REJECTS"),
]


def generate_cases(requirement_id: str, criterion_id: str | None = None,
                   policy_ids: list[str] | None = None) -> list[dict]:
    if not isinstance(requirement_id, str) or not requirement_id:
        raise ValueError("requirement_id is required")
    cases, seen = [], set()
    for name, technique, partition, start, end, overnight, meal, assertion in _DESIGNS:
        inputs = {"start_time": start, "end_time": end, "overnight": overnight,
                  "meal_break_minutes": meal}
        signature = (start, end, overnight, meal, assertion)
        if signature in seen:
            continue
        seen.add(signature)
        try:
            result = calculate(start, end, overnight, meal)
            expected = {"paid_minutes": result.paid_minutes,
                        "overtime_minutes": result.overtime_minutes}
            if assertion == "REJECTS":
                raise AssertionError("negative fixture unexpectedly valid")
        except DomainError:
            if assertion != "REJECTS":
                raise
            expected = {"status_code": 422}
        cases.append({"id": f"{requirement_id}-{name}", "version": 1,
                      "requirement_id": requirement_id,
                      "criterion_id": criterion_id, "policy_ids": list(policy_ids or POLICIES),
                      "rule_key": RULE_KEY, "technique": technique, "partition": partition,
                      "inputs": inputs, "assertion_type": assertion, "expected": expected,
                      "ai_claimed_expected": None, "validation_state": "DRAFT",
                      "approval_state": "PENDING"})
    return cases
