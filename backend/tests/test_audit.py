"""Audit hashing and audit-event tests."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.audit import canonical_json, sha256_hex
from app.core.contracts import AuditAction, RequirementStatus
from app.database.session import SessionLocal
from app.models import AuditEvent

RQ014_TEXT = (
    "For an overnight shift, calculate overtime correctly after the employee has worked "
    "the configured number of paid hours, excluding the unpaid meal break."
)
ACTOR = {"actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"}


def _events_for(entity_id: str) -> list[AuditEvent]:
    with SessionLocal() as session:
        return list(
            session.scalars(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(entity_id)))
        )


def test_canonical_json_sorts_keys_and_is_compact() -> None:
    assert canonical_json({"b": 1, "a": {"d": 2, "c": 3}}) == '{"a":{"c":3,"d":2},"b":1}'


def test_canonical_json_handles_uuid_dates_and_enums() -> None:
    value = uuid.UUID("12345678-1234-5678-1234-567812345678")
    data = {
        "id": value,
        "day": date(2026, 11, 4),
        "at": datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc),
        "status": RequirementStatus.DRAFT,
    }
    assert canonical_json(data) == (
        '{"at":"2026-11-04T10:00:00+00:00","day":"2026-11-04",'
        '"id":"12345678-1234-5678-1234-567812345678","status":"DRAFT"}'
    )


def test_naive_and_aware_utc_datetimes_hash_identically() -> None:
    naive = datetime(2026, 11, 4, 10, 0)
    aware_other_zone = datetime(2026, 11, 4, 15, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert sha256_hex({"at": naive}) == sha256_hex({"at": aware_other_zone})


def test_sha256_is_stable_and_none_for_none() -> None:
    assert sha256_hex({"a": 1, "b": 2}) == sha256_hex({"b": 2, "a": 1})
    assert len(sha256_hex({"a": 1}) or "") == 64
    assert sha256_hex(None) is None


def test_unserialisable_values_are_rejected() -> None:
    with pytest.raises(TypeError):
        canonical_json({"value": object()})


def test_creating_a_requirement_writes_audit_events(client: TestClient) -> None:
    code = f"RQ-{uuid.uuid4().int % 900000 + 100000}"
    response = client.post(
        "/requirements",
        headers={"X-Trace-ID": "audit-trace-001"},
        json={
            "code": code,
            "title": "Overnight overtime with unpaid meal break",
            "text": RQ014_TEXT,
            "policy_ids": ["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"],
            **ACTOR,
        },
    )
    assert response.status_code == 201
    body = response.json()

    requirement_events = _events_for(body["id"])
    assert len(requirement_events) == 1
    created = requirement_events[0]
    assert created.action == AuditAction.REQUIREMENT_CREATED
    assert created.actor == "asha.ba"
    assert created.trace_id == "audit-trace-001"
    assert created.before_hash is None
    assert created.after_hash == sha256_hex(
        {
            "id": body["id"],
            "code": code,
            "title": body["title"],
            "status": "DRAFT",
            "latest_version": 1,
        }
    )
    assert created.detail == {
        "code": code,
        "policy_ids": ["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"],
    }

    version_events = _events_for(body["versions"][0]["id"])
    assert [event.action for event in version_events] == [AuditAction.REQUIREMENT_VERSION_CREATED]
    version = body["versions"][0]
    assert version_events[0].after_hash == sha256_hex(
        {
            key: version[key]
            for key in ("id", "requirement_id", "version", "text", "policy_ids", "author", "change_note")
        }
    )


def test_creating_a_version_records_status_transition(client: TestClient) -> None:
    code = f"RQ-{uuid.uuid4().int % 900000 + 100000}"
    created = client.post(
        "/requirements",
        json={
            "code": code,
            "title": "Overnight overtime with unpaid meal break",
            "text": RQ014_TEXT,
            "policy_ids": ["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"],
            **ACTOR,
        },
    ).json()
    version = client.post(
        f"/requirements/{created['id']}/versions",
        json={
            "text": RQ014_TEXT,
            "policy_ids": ["POL-OT-01@v2", "POL-MEAL-02@v1", "POL-DATE-03@v1"],
            "change_note": "Threshold change.",
            **ACTOR,
        },
    ).json()

    events = _events_for(version["id"])
    assert len(events) == 1
    assert events[0].action == AuditAction.REQUIREMENT_VERSION_CREATED
    assert events[0].detail is not None
    assert events[0].detail["version"] == 2
    assert events[0].detail["requirement_status_before"] == "DRAFT"
    assert events[0].detail["requirement_status_after"] == "DRAFT"
