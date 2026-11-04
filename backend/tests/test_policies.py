"""Policy registry API and seed tests."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.seed import SeedConflictError, seed_reference_data
from app.models import Policy, SutVersion
from app.services.policy_service import utc_today


def _refs(response_json: list[dict[str, object]]) -> list[str]:
    return [str(item["ref"]) for item in response_json]


def test_default_listing_returns_only_policies_effective_today(client: TestClient) -> None:
    response = client.get("/policies")
    assert response.status_code == 200
    today = utc_today()
    for policy in response.json():
        assert policy["fictional"] is True
        assert date.fromisoformat(policy["effective_from"]) <= today
        if policy["effective_to"] is not None:
            assert today <= date.fromisoformat(policy["effective_to"])


def test_effective_on_returns_current_versions_in_2026(client: TestClient) -> None:
    response = client.get("/policies", params={"effective_on": "2026-11-04"})
    assert response.status_code == 200
    assert _refs(response.json()) == ["POL-DATE-03@v1", "POL-MEAL-02@v1", "POL-OT-01@v1"]


def test_effective_on_returns_revised_overtime_policy_in_2027(client: TestClient) -> None:
    response = client.get("/policies", params={"effective_on": "2027-02-01"})
    assert response.status_code == 200
    assert _refs(response.json()) == ["POL-DATE-03@v1", "POL-MEAL-02@v1", "POL-OT-01@v2"]


def test_include_all_versions_ignores_dates(client: TestClient) -> None:
    response = client.get("/policies", params={"include_all_versions": "true"})
    assert response.status_code == 200
    assert _refs(response.json()) == [
        "POL-DATE-03@v1",
        "POL-MEAL-02@v1",
        "POL-OT-01@v1",
        "POL-OT-01@v2",
    ]


def test_code_filter(client: TestClient) -> None:
    response = client.get(
        "/policies", params={"code": "POL-OT-01", "include_all_versions": "true"}
    )
    assert response.status_code == 200
    assert _refs(response.json()) == ["POL-OT-01@v1", "POL-OT-01@v2"]


@pytest.mark.parametrize(
    ("day", "expected"),
    [("2026-12-31", ["POL-OT-01@v1"]), ("2027-01-01", ["POL-OT-01@v2"]), ("2025-12-31", [])],
)
def test_effective_date_boundaries(
    client: TestClient, day: str, expected: list[str]
) -> None:
    response = client.get("/policies", params={"code": "POL-OT-01", "effective_on": day})
    assert response.status_code == 200
    assert _refs(response.json()) == expected


def test_invalid_code_is_rejected(client: TestClient) -> None:
    response = client.get("/policies", params={"code": "overtime"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_date_is_rejected(client: TestClient) -> None:
    response = client.get("/policies", params={"effective_on": "04-11-2026"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_seed_is_idempotent(db_session: Session) -> None:
    first = seed_reference_data(db_session)
    db_session.commit()
    second = seed_reference_data(db_session)
    db_session.commit()

    assert first.policies_created == 4 and first.sut_versions_created == 2
    assert second.policies_created == 0 and second.policies_existing == 4
    assert second.sut_versions_created == 0 and second.sut_versions_existing == 2
    assert db_session.scalar(select(func.count()).select_from(Policy)) == 4
    assert db_session.scalar(select(func.count()).select_from(SutVersion)) == 2


def test_seed_refuses_to_change_existing_policy_version(db_session: Session) -> None:
    seed_reference_data(db_session)
    db_session.commit()
    policy = db_session.scalar(
        select(Policy).where(Policy.policy_code == "POL-OT-01", Policy.version == 1)
    )
    assert policy is not None
    policy.rule_text = "Edited text"
    db_session.commit()

    with pytest.raises(SeedConflictError):
        seed_reference_data(db_session)
