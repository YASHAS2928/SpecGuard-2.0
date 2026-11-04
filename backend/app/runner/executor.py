"""Controlled HTTP runner; no model code, redirects, or arbitrary targets."""

from datetime import datetime, timezone
from time import perf_counter
from typing import Callable
import copy
import uuid
import httpx

from backend.app.engine.oracle import DomainError, calculate

TARGET = "http://127.0.0.1:9000/v1/pay/calculate"
VERSIONS = {"1.3.0", "1.3.0-b", "1.3.0-c", "1.4.0"}
ASSERTIONS = {"PAID_EQUALS", "OT_EQUALS", "REJECTS"}
MAX_CASES = 100
MAX_RESPONSE_BYTES = 16384


class ExecutionBlocked(ValueError):
    pass


def execute_cases(cases: list[dict], *, selected_version: str, issues: list[dict],
                  load_reviewed_case: Callable[[str], dict | None],
                  target: str = TARGET, client: httpx.Client | None = None) -> list[dict]:
    """Run only canonical, validated, reviewer-approved cases from trusted storage."""
    if target != TARGET:
        raise ExecutionBlocked("target is not the allowlisted mock endpoint")
    if selected_version not in VERSIONS:
        raise ExecutionBlocked("unrecognized mock version")
    if not isinstance(cases, list) or not 0 < len(cases) <= MAX_CASES:
        raise ExecutionBlocked("case count must be 1..100")
    if not isinstance(issues, list) or any(not isinstance(issue, dict) for issue in issues):
        raise ExecutionBlocked("validation findings must be supplied")
    if any(issue.get("severity") == "BLOCK" for issue in issues):
        raise ExecutionBlocked("blocking validation issue exists")
    if not callable(load_reviewed_case):
        raise ExecutionBlocked("trusted review lookup is required")
    ready_cases = []
    for case in cases:
        if not isinstance(case, dict) or not {"id", "version", "requirement_id", "policy_ids", "rule_key",
                "partition", "technique", "inputs", "assertion_type", "expected"} <= case.keys():
            raise ExecutionBlocked("case shape is invalid")
        if type(case["version"]) is not int or case["version"] < 1:
            raise ExecutionBlocked("case version is invalid")
        try:
            reviewed = load_reviewed_case(case["id"])
        except Exception as error:
            raise ExecutionBlocked("trusted review lookup failed") from error
        if not isinstance(reviewed, dict):
            raise ExecutionBlocked("case has no trusted review record")
        canonical = reviewed.get("case")
        recorded_issues = reviewed.get("issues")
        approval = reviewed.get("approval")
        if canonical != case or recorded_issues != issues:
            raise ExecutionBlocked("submitted case or findings differ from trusted state")
        if (not isinstance(approval, dict) or approval.get("test_id") != case["id"]
                or approval.get("case_version") != case.get("version")
                or approval.get("decision") != "APPROVED"
                or not approval.get("reviewer_id")):
            raise ExecutionBlocked("trusted human approval is missing or stale")
        if any(issue.get("severity") == "WARNING" for issue in issues) and not approval.get("warnings_acknowledged"):
            raise ExecutionBlocked("validation warning requires reviewer acknowledgment")
        if case.get("approval_state") != "APPROVED" or case.get("validation_state") != "VALID":
            raise ExecutionBlocked("test must be human-approved and validated")
        if case.get("assertion_type") not in ASSERTIONS:
            raise ExecutionBlocked("unsupported assertion type")
        if case.get("target") not in (None, TARGET):
            raise ExecutionBlocked("case contains forbidden target")
        if len(str(case.get("inputs", "")).encode()) > 2048:
            raise ExecutionBlocked("case payload exceeds 2048 bytes")
        ready_cases.append(copy.deepcopy(canonical))
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=httpx.Timeout(3.0, connect=1.0),
                              follow_redirects=False, trust_env=False)
    run_id = str(uuid.uuid4())
    results = []
    try:
        for case in ready_cases:
            began = perf_counter()
            assertion = case["assertion_type"]
            result = {"run_id": run_id, "test_id": case["id"],
                      "selected_version": selected_version, "assertion_type": assertion,
                      "expected": case["expected"], "actual": None, "status": "ERROR",
                      "error": None, "requirement_id": case["requirement_id"],
                      "criterion_id": case.get("criterion_id"), "policy_ids": case["policy_ids"],
                      "rule_key": case["rule_key"], "partition": case["partition"],
                      "technique": case["technique"],
                      "timestamp": datetime.now(timezone.utc).isoformat()}
            try:
                try:
                    oracle = calculate(**case["inputs"])
                    expected = {"paid_minutes": oracle.paid_minutes,
                                "overtime_minutes": oracle.overtime_minutes}
                    if assertion == "REJECTS":
                        raise ExecutionBlocked("REJECTS case is valid")
                except (DomainError, TypeError):
                    if assertion != "REJECTS":
                        raise ExecutionBlocked("oracle cannot calculate approved positive test")
                    expected = {"status_code": 422}
                if expected != case["expected"]:
                    raise ExecutionBlocked("approved expected value differs from oracle")
                response = client.post(target, json=case["inputs"], follow_redirects=False)
                if len(response.content) > MAX_RESPONSE_BYTES:
                    raise ValueError("mock response too large")
                if response.status_code in (301, 302, 303, 307, 308):
                    raise ValueError("mock redirect refused")
                if assertion == "REJECTS":
                    result["actual"] = {"status_code": response.status_code}
                    result["status"] = "PASS" if response.status_code == 422 else (
                        "ERROR" if response.status_code >= 500 else "FAIL")
                elif response.status_code != 200:
                    result["actual"] = {"status_code": response.status_code}
                    result["status"] = "ERROR" if response.status_code >= 500 else "FAIL"
                else:
                    if response.headers.get("X-Mock-Version") != selected_version:
                        raise ValueError("mock version response does not match selection")
                    data = response.json()
                    if (not isinstance(data, dict) or type(data.get("paid_minutes")) is not int
                            or type(data.get("overtime_minutes")) is not int
                            or data["paid_minutes"] < 0 or data["overtime_minutes"] < 0
                            or data["overtime_minutes"] > data["paid_minutes"]):
                        raise ValueError("invalid mock response schema")
                    result["actual"] = data
                    field = "paid_minutes" if assertion == "PAID_EQUALS" else "overtime_minutes"
                    result["status"] = "PASS" if data[field] == expected[field] else "FAIL"
            except (httpx.HTTPError, ValueError, ExecutionBlocked) as error:
                result["error"] = str(error)
            finally:
                result["duration_ms"] = round((perf_counter() - began) * 1000, 3)
                results.append(result)
    finally:
        if own_client:
            client.close()
    return results
