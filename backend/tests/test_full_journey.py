"""The complete demo journey through the real API, the real engine and the real mock API."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import MockServer
from flow_helpers import (
    BA, QA, RQ_TEXT, V1, V2, approve_engine_tests, approve_version, approved_spec, create_requirement, design,
    failing_codes, point_at, run,
)


@pytest.fixture()
def api(client: TestClient, mock_server: MockServer) -> Iterator[TestClient]:
    mock_server.use("1.3.0")
    point_at(client, mock_server.base_url)
    yield client
    mock_server.reset()  # never leak the runtime selection into other tests


def statuses(client: TestClient, spec_id: str) -> dict[str, str]:
    return {t["tc_code"]: t["status"] for t in client.get(f"/specs/{spec_id}/tests").json()}


def test_full_journey(api: TestClient, mock_server: MockServer) -> None:
    # 1. requirement -> analyse -> resolve -> approve
    requirement, spec1 = approved_spec(api, V1)
    assert spec1["status"] == "APPROVED" and all(r["grounded"] for r in spec1["rules"])

    # 2. design (engine + AI edge cases), review, run against the seeded-defect version
    designed = design(api, spec1["id"])
    assert len(designed["tests"]) == 17 and designed["blocked_count"] == 2
    approve_engine_tests(api, spec1["id"])
    seeded = run(api, spec1["id"])
    assert seeded["sut_version"] == "1.3.0" and seeded["totals"]["errors"] == 0
    overnight_failures = failing_codes(seeded)
    assert overnight_failures, "the overnight defect must be detected"
    open_defects = api.get("/defects", params={"spec_id": spec1["id"], "status": "OPEN"}).json()
    assert open_defects and any(d["partition"]["overnight"] is True for d in open_defects)
    failing = {r["tc_code"]: r for r in seeded["results"] if r["status"] == "FAIL"}
    assert all(r["failed_assertion"] and r["observed"] is not None for r in failing.values())

    # 3. fix (switch the mock) -> green -> defects FIXED, then VERIFIED
    mock_server.use("1.4.0")
    green = run(api, spec1["id"])
    assert green["totals"] == {"total": 14, "passed": 14, "failed": 0, "errors": 0}
    assert {d["status"] for d in api.get("/defects", params={"spec_id": spec1["id"]}).json()} == {"FIXED"}
    run(api, spec1["id"])
    assert {d["status"] for d in api.get("/defects", params={"spec_id": spec1["id"]}).json()} == {"VERIFIED"}

    # 4. new requirement version citing the announced policy -> analyse -> approve
    version = api.post(f"/requirements/{requirement['id']}/versions", json={
        "text": RQ_TEXT, "policy_ids": V2, "change_note": "POL-OT-01 v2 lowers the threshold to 450.", **BA})
    assert version.status_code == 201
    assert api.get(f"/requirements/{requirement['id']}").json()["status"] == "CHANGED"
    spec2 = approve_version(api, version.json()["id"])
    assert spec2["parent_spec_id"] == spec1["id"]
    assert next(r for r in spec2["rules"] if r["rule_key"] == "OT_THRESHOLD")["params"]["threshold"] == 450
    assert api.get(f"/specs/{spec1['id']}").json()["status"] == "SUPERSEDED"

    # 5. change impact: STALE / OBSOLETE / NEW / UNAFFECTED
    impact = api.post(f"/specs/{spec2['id']}/impact", json={**QA, "from_spec_id": spec1["id"]})
    assert impact.status_code == 201, impact.text
    report = impact.json()
    assert report["from_spec_id"] == spec1["id"] and report["to_spec_id"] == spec2["id"]
    assert report["counts"] == {"STALE_EXPECTED": 2, "OBSOLETE": 5, "NEW": 3, "UNAFFECTED": 10}  # 17 old tests
    # Wrong order (impact before design-tests on the new spec): behaviour is kept, the user is warned.
    assert len(report["warnings"]) == 2 and "design-tests" in report["warnings"][0]
    assert "2 AI-origin test(s)" in report["warnings"][1]
    reasons = {t["tc_code"]: t["reason"] for t in report["impacted_tests"] if t["impact_class"] == "OBSOLETE"}
    assert sum("AI edge case has no runnable counterpart" in r for r in reasons.values()) == 2
    assert {c["kind"] for c in report["rule_changes"]} == {"PARAM_CHANGED", "POLICY_VERSION_CHANGED"}
    param = next(c for c in report["rule_changes"] if c["kind"] == "PARAM_CHANGED")
    assert param["before"] == {"threshold": 480} and param["after"] == {"threshold": 450}
    stale = next(t for t in report["impacted_tests"] if t["impact_class"] == "STALE_EXPECTED")
    assert stale["old_expected"]["overtime_minutes"] == 30 and stale["new_expected"]["overtime_minutes"] == 60
    assert stale["replacement_test_id"] in report["rerun_test_ids"] and len(report["rerun_test_ids"]) == 4
    assert report["impacted_criteria"] and report["created_at"].endswith(("Z", "+00:00"))
    old_status = statuses(api, spec1["id"])
    # Approved stale tests become STALE, scenarios that are no longer designed become OBSOLETE (including the
    # 2 AI tests that this spec's engine-only design does not regenerate); a BLOCKED test keeps its status.
    assert sorted(set(old_status.values())) == ["APPROVED", "BLOCKED", "OBSOLETE", "STALE"]
    assert list(old_status.values()).count("OBSOLETE") == 5 and list(old_status.values()).count("STALE") == 1
    assert list(old_status.values()).count("APPROVED") == 10
    again = api.post(f"/specs/{spec2['id']}/impact", json={**QA, "from_spec_id": spec1["id"]})
    assert again.status_code == 409

    # 6. the old (superseded) spec cannot be run, and its stale/obsolete tests are not runnable
    assert api.post("/runs", json={**QA, "spec_id": spec1["id"]}).status_code == 409

    # 7. new tests are DRAFT, linked to the old ones; humans re-approve
    new_tests = api.get(f"/specs/{spec2['id']}/tests").json()
    assert len(new_tests) == 14 and {t["status"] for t in new_tests} == {"DRAFT"}
    assert len([t for t in new_tests if t["supersedes_id"]]) == 11
    assert api.post("/runs", json={**QA, "spec_id": spec2["id"]}).status_code == 409  # nothing approved yet
    approve_engine_tests(api, spec2["id"])

    # 8. drift: the 1.4.0 implementation still uses 480 -> new expectations fail
    drift = run(api, spec2["id"], trigger="IMPACT_RERUN")
    assert drift["sut_version"] == "1.4.0" and drift["totals"]["errors"] == 0
    drift_failures = failing_codes(drift)
    expected_codes = {t["tc_code"] for t in new_tests if t["expected"]["overtime_minutes"] not in (None, 0)}
    assert drift_failures and drift_failures <= {t["tc_code"] for t in new_tests}
    assert drift_failures >= {t["tc_code"] for t in new_tests if t["inputs"]["end_time"] == "15:31"}
    assert expected_codes >= drift_failures
    assert any(d["status"] == "OPEN" for d in api.get("/defects", params={"spec_id": spec2["id"]}).json())

    # 9. switch to 1.5.0 (the announced change) -> green
    mock_server.use("1.5.0")
    final = run(api, spec2["id"])
    assert final["sut_version"] == "1.5.0"
    assert final["totals"] == {"total": 14, "passed": 14, "failed": 0, "errors": 0}
    assert {d["status"] for d in api.get("/defects", params={"spec_id": spec2["id"]}).json()} == {"FIXED"}

    # 10. metrics and audit tell the same story
    metrics = api.get("/metrics/overview").json()
    assert metrics["last_run"]["run_id"] == final["id"] and metrics["last_run"]["totals"]["passed"] == 14
    assert metrics["tests_by_status"]["STALE"] >= 1 and metrics["tests_by_status"]["OBSOLETE"] >= 3
    trail = api.get("/audit", params={"entity_type": "CHANGE_IMPACT"}).json()
    assert trail["items"] and trail["items"][0]["action"] == "CHANGE_IMPACT_ANALYZED"
    assert trail["items"][0]["detail"]["counts"] == report["counts"]
    spec_actions = {e["action"] for e in api.get("/audit", params={"entity_id": spec1["id"], "limit": 500}).json()["items"]}
    assert {"REQUIREMENT_ANALYZED", "SPEC_APPROVED", "SPEC_SUPERSEDED", "TESTS_DESIGNED"} <= spec_actions
    for item in api.get("/audit", params={"limit": 500}).json()["items"]:
        assert item["ts"].endswith(("Z", "+00:00")) and item["actor"]


def test_impact_works_after_tests_were_designed_for_the_new_spec_with_ai(api: TestClient) -> None:
    requirement, spec1 = approved_spec(api, V1)
    design(api, spec1["id"], ai=False)
    approve_engine_tests(api, spec1["id"])
    version = api.post(f"/requirements/{requirement['id']}/versions",
                       json={"text": RQ_TEXT, "policy_ids": V2, "change_note": "Policy change.", **BA}).json()
    spec2 = approve_version(api, version["id"])
    design(api, spec2["id"])  # AI edge cases included: impact must reuse these tests, not duplicate them
    report = api.post(f"/specs/{spec2['id']}/impact", json={**QA, "from_spec_id": spec1["id"]}).json()
    assert len(api.get(f"/specs/{spec2['id']}/tests").json()) == 17
    assert report["counts"]["STALE_EXPECTED"] == 1 and report["counts"]["OBSOLETE"] == 3


def test_impact_after_designing_the_new_spec_with_ai_classifies_ai_tests_by_the_oracle(api: TestClient) -> None:
    """Correct order: approve new spec -> design-tests on it (with AI) -> impact."""
    requirement, spec1 = approved_spec(api, V1)
    old = design(api, spec1["id"])
    approve_engine_tests(api, spec1["id"])
    old_by_code = {t["tc_code"]: t for t in old["tests"]}
    version = api.post(f"/requirements/{requirement['id']}/versions",
                       json={"text": RQ_TEXT, "policy_ids": V2, "change_note": "Policy change.", **BA}).json()
    spec2 = approve_version(api, version["id"])
    new = design(api, spec2["id"])
    assert (new["added"], len(new["tests"]), new["blocked_count"]) == (17, 17, 2)

    report = api.post(f"/specs/{spec2['id']}/impact", json={**QA, "from_spec_id": spec1["id"]}).json()
    assert report["warnings"] == []
    assert report["counts"] == {"STALE_EXPECTED": 2, "OBSOLETE": 4, "NEW": 3, "UNAFFECTED": 11}  # 17 old tests
    assert len(api.get(f"/specs/{spec2['id']}/tests").json()) == 17  # impact reused the designed tests

    by_class: dict[str, list[dict[str, Any]]] = {}
    for item in report["impacted_tests"]:
        by_class.setdefault(item["impact_class"], []).append(item)
    ai_items = {i["tc_code"]: i for cls in ("STALE_EXPECTED", "OBSOLETE", "UNAFFECTED") for i in by_class[cls]
                if old_by_code[i["tc_code"]]["origin"] == "AI"}
    classes = {code: item["impact_class"] for code, item in ai_items.items()}
    draft_ai = next(c for c, t in old_by_code.items() if t["origin"] == "AI" and t["status"] == "DRAFT")
    blocked_ai = [c for c, t in old_by_code.items() if t["origin"] == "AI" and t["status"] == "BLOCKED"]
    assert classes[draft_ai] == "UNAFFECTED"  # the AI edge case still exists, oracle value unchanged
    assert sorted(classes[c] for c in blocked_ai) == ["OBSOLETE", "STALE_EXPECTED"]
    obsolete_ai = next(ai_items[c] for c in blocked_ai if classes[c] == "OBSOLETE")
    assert "no runnable counterpart" in obsolete_ai["reason"]
    assert len(report["rerun_test_ids"]) == 4 and len(set(report["rerun_test_ids"])) == 4
    # the AI draft test of the new spec supersedes the old one and needs re-approval
    new_ai = next(t for t in api.get(f"/specs/{spec2['id']}/tests", params={"origin": "AI", "status": "DRAFT"}).json())
    assert new_ai["supersedes_id"] == old_by_code[draft_ai]["id"]


def test_a_superseded_spec_can_be_the_from_spec_and_an_unchanged_spec_has_no_impact(api: TestClient) -> None:
    requirement, spec1 = approved_spec(api, V1)
    design(api, spec1["id"], ai=False)
    approve_engine_tests(api, spec1["id"])
    version = api.post(f"/requirements/{requirement['id']}/versions",
                       json={"text": RQ_TEXT + " Clarified wording only.", "policy_ids": V1, "change_note": "Wording.", **BA}).json()
    spec2 = approve_version(api, version["id"])
    assert api.get(f"/specs/{spec1['id']}").json()["status"] == "SUPERSEDED"
    report = api.post(f"/specs/{spec2['id']}/impact", json={**QA, "from_spec_id": spec1["id"]}).json()
    assert report["counts"] == {"STALE_EXPECTED": 0, "OBSOLETE": 0, "NEW": 0, "UNAFFECTED": 14}
    assert report["rule_changes"] == [] and report["rerun_test_ids"] == [] and report["impacted_criteria"] == []
