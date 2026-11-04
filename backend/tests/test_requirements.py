"""Requirement and requirement-version API tests."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.contracts import RequirementCreate, RequirementStatus, RequirementVersionCreate
from app.database.seed import seed_reference_data
from app.database.session import SessionLocal
from app.models import AuditEvent, Requirement, RequirementVersion
from app.services import requirement_service

RQ014_TEXT = (
    "For an overnight shift, calculate overtime correctly after the employee has worked "
    "the configured number of paid hours, excluding the unpaid meal break."
)
V1_POLICIES = ["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"]
V2_POLICIES = ["POL-OT-01@v2", "POL-MEAL-02@v1", "POL-DATE-03@v1"]
ACTOR = {"actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"}


def unique_code() -> str:
    """Return a requirement code unlikely to collide across tests sharing one database."""
    return f"RQ-{uuid.uuid4().int % 900000 + 100000}"


def requirement_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": unique_code(),
        "title": "Overnight overtime with unpaid meal break",
        "text": RQ014_TEXT,
        "policy_ids": V1_POLICIES,
        **ACTOR,
    }
    payload.update(overrides)
    return payload


def create_requirement(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/requirements", json=requirement_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def test_create_requirement_returns_draft_with_version_one(client: TestClient) -> None:
    body = create_requirement(client)
    assert uuid.UUID(body["id"])
    assert body["status"] == "DRAFT"
    assert body["latest_version"] == 1
    version = body["versions"][0]
    assert version["version"] == 1
    assert version["author"] == "asha.ba"
    assert version["policy_ids"] == V1_POLICIES
    assert version["requirement_id"] == body["id"]


def test_duplicate_code_returns_conflict(client: TestClient) -> None:
    payload = requirement_payload()
    assert client.post("/requirements", json=payload).status_code == 201
    response = client.post("/requirements", json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_unknown_policy_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/requirements", json=requirement_payload(policy_ids=["POL-OT-99@v1", "POL-MEAL-02@v1"])
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"] == {"unknown_policy_ids": ["POL-OT-99@v1"]}


def test_two_versions_of_the_same_policy_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/requirements", json=requirement_payload(policy_ids=["POL-OT-01@v1", "POL-OT-01@v2"])
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"duplicate_policy_codes": ["POL-OT-01"]}


def test_system_role_cannot_create_requirements(client: TestClient) -> None:
    response = client.post("/requirements", json=requirement_payload(actor_role="SYSTEM"))
    assert response.status_code == 422


def test_get_requirement(client: TestClient) -> None:
    created = create_requirement(client)
    response = client.get(f"/requirements/{created['id']}")
    assert response.status_code == 200
    assert response.json()["code"] == created["code"]


def test_requirement_timestamps_remain_utc_after_reload(client: TestClient) -> None:
    created = create_requirement(client)
    response = client.get(f"/requirements/{created['id']}")
    assert response.status_code == 200
    retrieved = response.json()
    assert retrieved == created
    for field in ("created_at", "updated_at"):
        assert retrieved[field] == created[field]
        assert retrieved[field].endswith(("Z", "+00:00"))
    assert retrieved["versions"][0]["created_at"].endswith(("Z", "+00:00"))


def test_get_unknown_requirement_returns_404(client: TestClient) -> None:
    response = client.get(f"/requirements/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_get_with_invalid_uuid_returns_422(client: TestClient) -> None:
    response = client.get("/requirements/123")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_requirements_includes_created(client: TestClient) -> None:
    created = create_requirement(client)
    response = client.get("/requirements")
    assert response.status_code == 200
    assert created["id"] in {item["id"] for item in response.json()}


def test_create_version_appends_version_two(client: TestClient) -> None:
    created = create_requirement(client)
    response = client.post(
        f"/requirements/{created['id']}/versions",
        json={
            "text": RQ014_TEXT,
            "policy_ids": V2_POLICIES,
            "change_note": "POL-OT-01 v2 lowers the overtime threshold to 450 minutes.",
            **ACTOR,
        },
    )
    assert response.status_code == 201, response.text
    version = response.json()
    assert version["version"] == 2
    assert version["policy_ids"] == V2_POLICIES

    requirement = client.get(f"/requirements/{created['id']}").json()
    assert requirement["latest_version"] == 2
    assert [v["version"] for v in requirement["versions"]] == [1, 2]
    assert requirement["versions"][0]["policy_ids"] == V1_POLICIES
    assert requirement["status"] == "DRAFT"


def test_identical_version_returns_conflict(client: TestClient) -> None:
    created = create_requirement(client)
    response = client.post(
        f"/requirements/{created['id']}/versions",
        json={"text": RQ014_TEXT, "policy_ids": list(reversed(V1_POLICIES)), **ACTOR},
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"latest_version": 1}


def test_version_for_unknown_requirement_returns_404(client: TestClient) -> None:
    response = client.post(
        f"/requirements/{uuid.uuid4()}/versions",
        json={"text": RQ014_TEXT, "policy_ids": V2_POLICIES, **ACTOR},
    )
    assert response.status_code == 404


def test_version_with_unknown_policy_is_rejected(client: TestClient) -> None:
    created = create_requirement(client)
    response = client.post(
        f"/requirements/{created['id']}/versions",
        json={"text": RQ014_TEXT, "policy_ids": ["POL-OT-01@v9"], **ACTOR},
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"unknown_policy_ids": ["POL-OT-01@v9"]}
    requirement = client.get(f"/requirements/{created['id']}").json()
    assert requirement == created


@pytest.mark.parametrize(
    ("previous", "expected"),
    [
        (RequirementStatus.DRAFT, RequirementStatus.DRAFT),
        (RequirementStatus.ANALYZED, RequirementStatus.DRAFT),
        (RequirementStatus.SPEC_APPROVED, RequirementStatus.CHANGED),
        (RequirementStatus.CHANGED, RequirementStatus.CHANGED),
    ],
)
def test_new_version_updates_status_and_preserves_history(
    db_session: Session, previous: RequirementStatus, expected: RequirementStatus
) -> None:
    seed_reference_data(db_session)
    requirement = requirement_service.create_requirement(
        db_session, RequirementCreate(**requirement_payload()), trace_id="status-test"
    )
    original = requirement_service.version_snapshot(requirement.versions[0])
    requirement.status = previous
    db_session.commit()
    version = requirement_service.create_version(
        db_session,
        requirement.id,
        RequirementVersionCreate(text=RQ014_TEXT, policy_ids=V2_POLICIES, **ACTOR),
        trace_id="status-test",
    )
    db_session.expire_all()
    persisted = requirement_service.get_requirement(db_session, requirement.id)
    assert persisted.status == expected
    assert [item.version for item in persisted.versions] == [1, 2]
    assert requirement_service.version_snapshot(persisted.versions[0]) == original
    event = db_session.scalar(select(AuditEvent).where(AuditEvent.entity_id == version.id))
    assert event is not None and event.detail is not None
    assert event.detail["requirement_status_before"] == previous.value
    assert event.detail["requirement_status_after"] == expected.value


def test_requirement_and_audits_roll_back_together(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = requirement_payload()
    with SessionLocal() as db:
        audit_count = db.scalar(select(func.count()).select_from(AuditEvent))
        version_count = db.scalar(select(func.count()).select_from(RequirementVersion))

    record = requirement_service.record_audit_event
    calls = 0

    def fail_second_audit(*args: Any, **kwargs: Any) -> AuditEvent:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Synthetic audit failure")
        return record(*args, **kwargs)

    monkeypatch.setattr(requirement_service, "record_audit_event", fail_second_audit)
    with pytest.raises(RuntimeError, match="Synthetic audit failure"):
        client.post("/requirements", json=payload)

    with SessionLocal() as db:
        assert db.scalar(select(Requirement).where(Requirement.code == payload["code"])) is None
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == audit_count
        assert db.scalar(select(func.count()).select_from(RequirementVersion)) == version_count


def test_version_and_status_roll_back_if_audit_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = create_requirement(client)
    requirement_id = uuid.UUID(created["id"])
    with SessionLocal() as db:
        requirement = db.get(Requirement, requirement_id)
        assert requirement is not None
        requirement.status = RequirementStatus.SPEC_APPROVED
        db.commit()
    before = client.get(f"/requirements/{requirement_id}").json()

    def fail_audit(*args: Any, **kwargs: Any) -> AuditEvent:
        raise RuntimeError("Synthetic audit failure")

    monkeypatch.setattr(requirement_service, "record_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="Synthetic audit failure"):
        client.post(
            f"/requirements/{requirement_id}/versions",
            json={"text": RQ014_TEXT, "policy_ids": V2_POLICIES, **ACTOR},
        )
    assert client.get(f"/requirements/{requirement_id}").json() == before
