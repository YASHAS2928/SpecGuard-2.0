"""Database model tests: schema, UUID keys, constraints, cascades and audit immutability."""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.contracts import (
    ActorRole,
    AuditAction,
    EntityType,
    PolicyResponse,
    RequirementResponse,
    RuleOrigin,
    RuleType,
    RunTrigger,
)
from app.database.init_db import init_db
from app.database.session import create_db_engine
from app.models import (
    AuditEvent,
    AuditImmutableError,
    Policy,
    Requirement,
    RequirementVersion,
    Run,
    Spec,
    SpecRule,
    TraceLink,
    TraceLinkType,
)

EXPECTED_TABLES = {
    "ambiguities",
    "audit_events",
    "change_impacts",
    "criteria",
    "defects",
    "eval_runs",
    "llm_calls",
    "policies",
    "requirement_versions",
    "requirements",
    "results",
    "reviews",
    "runs",
    "spec_rules",
    "specs",
    "sut_versions",
    "test_cases",
    "trace_links",
    "validation_issues",
}

RQ014_TEXT = (
    "For an overnight shift, calculate overtime correctly after the employee has worked "
    "the configured number of paid hours, excluding the unpaid meal break."
)


def _requirement_with_version(db: Session) -> tuple[Requirement, RequirementVersion]:
    requirement = Requirement(code="RQ-014", title="Overnight overtime with unpaid meal break")
    version = RequirementVersion(
        version=1,
        text=RQ014_TEXT,
        policy_ids=["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"],
        author="asha.ba",
    )
    requirement.versions.append(version)
    db.add(requirement)
    db.flush()
    return requirement, version


def _policy(**overrides: object) -> Policy:
    rule_text = "For this mock business only: paid minutes above 480 in a single shift are overtime."
    values: dict[str, object] = {
        "policy_code": "POL-OT-01",
        "version": 1,
        "title": "Overtime threshold (fictional)",
        "rule_text": rule_text,
        "effective_from": date(2026, 1, 1),
        "effective_to": date(2026, 12, 31),
        "sha256": hashlib.sha256(rule_text.encode("utf-8")).hexdigest(),
    }
    values.update(overrides)
    return Policy(**values)


def test_all_nineteen_tables_are_created() -> None:
    engine = create_db_engine("sqlite://")
    try:
        tables = set(init_db(engine))
        assert tables == EXPECTED_TABLES
        assert set(init_db(engine)) == EXPECTED_TABLES
    finally:
        engine.dispose()


def test_primary_keys_are_uuids_stored_as_hex_text(db_session: Session) -> None:
    requirement, version = _requirement_with_version(db_session)
    assert isinstance(requirement.id, uuid.UUID)
    assert isinstance(version.id, uuid.UUID)
    assert version.requirement_id == requirement.id
    stored = db_session.execute(text("SELECT id FROM requirements")).scalar_one()
    assert stored == requirement.id.hex


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 11, 4, 10, 0),
        datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 4, 15, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))),
    ],
)
def test_timestamps_are_stored_as_utc_and_loaded_with_utc_timezone(
    db_session: Session, timestamp: datetime
) -> None:
    requirement = Requirement(
        code="RQ-014", title="UTC timestamps", created_at=timestamp, updated_at=timestamp
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)

    expected = datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)
    for value in (requirement.created_at, requirement.updated_at):
        assert value.tzinfo == timezone.utc
        assert value == expected
    stored = db_session.execute(text("SELECT created_at, updated_at FROM requirements")).one()
    assert tuple(stored) == ("2026-11-04 10:00:00.000000",) * 2


def test_foreign_keys_are_enforced(db_session: Session) -> None:
    orphan = RequirementVersion(
        requirement_id=uuid.uuid4(), version=1, text=RQ014_TEXT, policy_ids=[], author="asha.ba"
    )
    db_session.add(orphan)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_requirement_with_versions_cannot_be_deleted(db_session: Session) -> None:
    requirement, version = _requirement_with_version(db_session)
    db_session.add(Spec(requirement_version_id=version.id, version=1))
    db_session.commit()

    db_session.delete(requirement)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    persisted_requirement = db_session.get(Requirement, requirement.id)
    persisted_version = db_session.get(RequirementVersion, version.id)
    assert persisted_requirement is not None
    assert persisted_version is not None
    assert persisted_version.requirement_id == requirement.id
    assert db_session.scalar(select(func.count()).select_from(Spec)) == 1


def test_requirement_and_versions_can_be_created_normally(db_session: Session) -> None:
    requirement = Requirement(code="RQ-015", title="Versioned meal-break requirement")
    first_version = RequirementVersion(
        version=1,
        text=RQ014_TEXT,
        policy_ids=["POL-MEAL-02@v1"],
        author="asha.ba",
    )
    second_version = RequirementVersion(
        version=2,
        text=f"{RQ014_TEXT} Updated clarification.",
        policy_ids=["POL-MEAL-02@v2"],
        author="asha.ba",
        change_note="Updated meal-break policy.",
    )
    requirement.versions.extend([first_version, second_version])
    db_session.add(requirement)
    db_session.commit()

    assert requirement.latest_version == 2
    assert first_version.requirement_id == requirement.id
    assert second_version.requirement_id == requirement.id
    assert db_session.get(RequirementVersion, first_version.id) is not None
    assert db_session.get(RequirementVersion, second_version.id) is not None


def test_requirement_version_numbers_are_unique(db_session: Session) -> None:
    requirement, _ = _requirement_with_version(db_session)
    db_session.add(
        RequirementVersion(
            requirement_id=requirement.id, version=1, text=RQ014_TEXT, policy_ids=[], author="x"
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_enum_check_constraint_rejects_unknown_values(db_session: Session) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO requirements (id, code, title, status, created_at, updated_at) "
                "VALUES (:id, 'RQ-999', 'Bad status', 'BOGUS', :ts, :ts)"
            ),
            {"id": uuid.uuid4().hex, "ts": now},
        )


def test_spec_rule_keys_are_unique_per_spec(db_session: Session) -> None:
    _, version = _requirement_with_version(db_session)
    spec = Spec(requirement_version_id=version.id, version=1)
    rule_args = {
        "rule_key": "OT_THRESHOLD",
        "type": RuleType.THRESHOLD,
        "params": {"threshold": 480},
        "origin": RuleOrigin.POLICY,
        "policy_ref": "POL-OT-01@v1",
        "source_span": "paid minutes above 480 in a single shift are overtime",
    }
    spec.rules.append(SpecRule(**rule_args))
    spec.rules.append(SpecRule(**rule_args))
    db_session.add(spec)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_json_columns_track_top_level_mutations(db_session: Session) -> None:
    _, version = _requirement_with_version(db_session)
    spec = Spec(requirement_version_id=version.id, version=1)
    rule = SpecRule(
        rule_key="OT_THRESHOLD",
        type=RuleType.THRESHOLD,
        params={"threshold": 480, "comparison": "gt"},
        origin=RuleOrigin.POLICY,
        policy_ref="POL-OT-01@v1",
        source_span="paid minutes above 480 in a single shift are overtime",
    )
    spec.rules.append(rule)
    db_session.add(spec)
    db_session.commit()

    rule.params["threshold"] = 450
    db_session.commit()
    db_session.expire_all()

    reloaded = db_session.get(SpecRule, rule.id)
    assert reloaded is not None
    assert reloaded.params == {"threshold": 450, "comparison": "gt"}


def test_run_totals_must_be_consistent(db_session: Session) -> None:
    _, version = _requirement_with_version(db_session)
    spec = Spec(requirement_version_id=version.id, version=1)
    db_session.add(spec)
    db_session.flush()
    db_session.add(
        Run(
            spec_id=spec.id,
            sut_version="1.3.0",
            trigger=RunTrigger.MANUAL,
            actor="ravi.qa",
            total=1,
            passed=2,
            failed=0,
            errors=0,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_trace_links_are_unique(db_session: Session) -> None:
    from_id, to_id = uuid.uuid4(), uuid.uuid4()
    link_args = {
        "from_type": EntityType.TEST_CASE,
        "from_id": from_id,
        "to_type": EntityType.RULE,
        "to_id": to_id,
        "link_type": TraceLinkType.VERIFIES,
    }
    db_session.add(TraceLink(**link_args))
    db_session.flush()
    db_session.add(TraceLink(**link_args))
    with pytest.raises(IntegrityError):
        db_session.flush()


def _audit_event(db: Session) -> AuditEvent:
    event_row = AuditEvent(
        actor="asha.ba",
        actor_role=ActorRole.BUSINESS_ANALYST,
        action=AuditAction.REQUIREMENT_CREATED,
        entity_type=EntityType.REQUIREMENT,
        entity_id=uuid.uuid4(),
        after_hash="a" * 64,
        trace_id="demo-trace-001",
    )
    db.add(event_row)
    db.commit()
    return event_row


def test_inferred_datetime_columns_load_with_utc_timezone(db_session: Session) -> None:
    event_row = _audit_event(db_session)
    timestamp = event_row.ts
    db_session.refresh(event_row)
    assert event_row.ts.tzinfo == timezone.utc
    assert event_row.ts == timestamp


def test_audit_events_cannot_be_updated(db_session: Session) -> None:
    event_row = _audit_event(db_session)
    event_row.actor = "someone.else"
    with pytest.raises(AuditImmutableError):
        db_session.flush()


def test_audit_events_cannot_be_deleted(db_session: Session) -> None:
    event_row = _audit_event(db_session)
    db_session.delete(event_row)
    with pytest.raises(AuditImmutableError):
        db_session.flush()


def test_policy_effective_range_is_checked(db_session: Session) -> None:
    db_session.add(_policy(effective_from=date(2026, 6, 1), effective_to=date(2026, 1, 1)))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_policy_maps_to_policy_response_contract(db_session: Session) -> None:
    policy = _policy()
    db_session.add(policy)
    db_session.flush()

    response = PolicyResponse.model_validate(policy)
    assert response.id == policy.id
    assert response.ref == "POL-OT-01@v1"
    assert policy.is_effective_on(date(2026, 11, 4))
    assert not policy.is_effective_on(date(2027, 1, 1))


def test_requirement_maps_to_requirement_response_contract(db_session: Session) -> None:
    requirement, version = _requirement_with_version(db_session)
    db_session.commit()

    response = RequirementResponse.model_validate(requirement)
    assert response.id == requirement.id
    assert response.status == "DRAFT"
    assert response.latest_version == 1
    assert response.versions[0].id == version.id
    assert response.versions[0].policy_ids == [
        "POL-OT-01@v1",
        "POL-MEAL-02@v1",
        "POL-DATE-03@v1",
    ]


def test_schema_has_expected_indexes() -> None:
    engine = create_db_engine("sqlite://")
    try:
        init_db(engine)
        inspector = inspect(engine)
        audit_indexes = {index["name"] for index in inspector.get_indexes("audit_events")}
        assert "ix_audit_events_entity" in audit_indexes
        test_indexes = {index["name"] for index in inspector.get_indexes("test_cases")}
        assert "ix_test_cases_spec_id_status" in test_indexes
    finally:
        engine.dispose()
