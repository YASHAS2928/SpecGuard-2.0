"""Helpers shared by the API-level flow tests."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings

RQ_TEXT = (
    "For an overnight shift, calculate overtime correctly after the employee has worked "
    "the configured number of paid hours, excluding the unpaid meal break."
)
V1 = ["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"]
V2 = ["POL-OT-01@v2", "POL-MEAL-02@v1", "POL-DATE-03@v1"]
BA = {"actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"}
QA = {"actor": "ravi.qa", "actor_role": "QA_ENGINEER"}
DEV = {"actor": "dev.one", "actor_role": "DEVELOPER"}


def point_at(client: TestClient, base_url: str) -> None:
    """Use the fake AI provider and the given mock API for this client's app."""
    client.app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[attr-defined]
        _env_file=None, ai_provider="fake", mock_api_base_url=base_url, log_level="WARNING")


def create_requirement(client: TestClient, policies: list[str] = V1, text: str = RQ_TEXT) -> dict[str, Any]:
    response = client.post("/requirements", json={
        "code": f"RQ-{uuid.uuid4().int % 900000 + 100000}", "title": "Overnight overtime", "text": text,
        "policy_ids": policies, **BA})
    assert response.status_code == 201, response.text
    return response.json()


def approve_version(client: TestClient, version_id: str) -> dict[str, Any]:
    analysis = client.post(f"/requirement-versions/{version_id}/analyze", json=BA)
    assert analysis.status_code == 200, analysis.text
    spec = analysis.json()["spec"]
    for ambiguity in spec["ambiguities"]:
        resolved = client.post(f"/ambiguities/{ambiguity['id']}/resolve", json={**BA, "option_index": 0})
        assert resolved.status_code == 200, resolved.text
    approved = client.post(f"/specs/{spec['id']}/approve", json=BA)
    assert approved.status_code == 200, approved.text
    return approved.json()


def approved_spec(client: TestClient, policies: list[str] = V1, text: str = RQ_TEXT) -> tuple[dict[str, Any], dict[str, Any]]:
    requirement = create_requirement(client, policies, text)
    return requirement, approve_version(client, requirement["versions"][0]["id"])


def design(client: TestClient, spec_id: str, ai: bool = True, who: dict[str, str] = QA) -> dict[str, Any]:
    response = client.post(f"/specs/{spec_id}/design-tests", json={**who, "include_ai_edge_cases": ai})
    assert response.status_code == 200, response.text
    return response.json()


def approve_engine_tests(client: TestClient, spec_id: str) -> dict[str, Any]:
    tests = client.get(f"/specs/{spec_id}/tests", params={"origin": "ENGINE", "status": "DRAFT"}).json()
    response = client.post("/tests/review", json={**QA, "decision": "APPROVE", "test_ids": [t["id"] for t in tests]})
    assert response.status_code == 200, response.text
    return response.json()


def run(client: TestClient, spec_id: str, **extra: Any) -> dict[str, Any]:
    response = client.post("/runs", json={**QA, "spec_id": spec_id, "test_ids": None, "trigger": "MANUAL", **extra})
    assert response.status_code == 201, response.text
    return response.json()


def failing_codes(run_body: dict[str, Any]) -> set[str]:
    return {r["tc_code"] for r in run_body["results"] if r["status"] == "FAIL"}
