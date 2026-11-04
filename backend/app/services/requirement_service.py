"""Requirement creation, versioning and retrieval, with audit events.

Requirement versions are immutable. Creating a version never edits an earlier
one; it appends version N+1 and updates the requirement's status.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.audit import record_audit_event
from app.core.contracts import (
    AuditAction,
    EntityType,
    RequirementCreate,
    RequirementStatus,
    RequirementVersionCreate,
)
from app.core.errors import ConflictError, NotFoundError
from app.database.base import utc_now
from app.models import Requirement, RequirementVersion
from app.services.policy_service import resolve_policy_refs


def _requirement_query() -> Select[tuple[Requirement]]:
    return select(Requirement).options(selectinload(Requirement.versions))


def requirement_snapshot(requirement: Requirement) -> dict[str, Any]:
    """Return the audit snapshot of a requirement."""
    return {
        "id": str(requirement.id),
        "code": requirement.code,
        "title": requirement.title,
        "status": RequirementStatus(requirement.status).value,
        "latest_version": requirement.latest_version,
    }


def version_snapshot(version: RequirementVersion) -> dict[str, Any]:
    """Return the audit snapshot of a requirement version."""
    return {
        "id": str(version.id),
        "requirement_id": str(version.requirement_id),
        "version": version.version,
        "text": version.text,
        "policy_ids": list(version.policy_ids),
        "author": version.author,
        "change_note": version.change_note,
    }


def _status_after_new_version(current: RequirementStatus) -> RequirementStatus:
    """A new version invalidates earlier analysis; approved work becomes CHANGED."""
    if current in (RequirementStatus.SPEC_APPROVED, RequirementStatus.CHANGED):
        return RequirementStatus.CHANGED
    return RequirementStatus.DRAFT


def get_requirement(db: Session, requirement_id: uuid.UUID) -> Requirement:
    """Return a requirement with its versions, or raise 404."""
    requirement = db.scalars(_requirement_query().where(Requirement.id == requirement_id)).first()
    if requirement is None:
        raise NotFoundError(
            f"Requirement {requirement_id} was not found.",
            details={"requirement_id": str(requirement_id)},
        )
    return requirement


def list_requirements(db: Session) -> list[Requirement]:
    """Return all requirements ordered by code."""
    return list(db.scalars(_requirement_query().order_by(Requirement.code)))


def create_requirement(
    db: Session, payload: RequirementCreate, *, trace_id: str | None
) -> Requirement:
    """Create a requirement with version 1 in one transaction, and audit it."""
    if db.scalar(select(Requirement.id).where(Requirement.code == payload.code)) is not None:
        raise ConflictError(
            f"Requirement code {payload.code} already exists.", details={"code": payload.code}
        )
    resolve_policy_refs(db, payload.policy_ids)

    requirement = Requirement(code=payload.code, title=payload.title, status=RequirementStatus.DRAFT)
    version = RequirementVersion(
        version=1,
        text=payload.text,
        policy_ids=list(payload.policy_ids),
        author=payload.actor,
        change_note=None,
    )
    requirement.versions.append(version)
    db.add(requirement)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Requirement code {payload.code} already exists.", details={"code": payload.code}
        ) from exc

    record_audit_event(
        db,
        actor=payload.actor,
        actor_role=payload.actor_role,
        action=AuditAction.REQUIREMENT_CREATED,
        entity_type=EntityType.REQUIREMENT,
        entity_id=requirement.id,
        after=requirement_snapshot(requirement),
        trace_id=trace_id,
        detail={"code": requirement.code, "policy_ids": list(version.policy_ids)},
    )
    record_audit_event(
        db,
        actor=payload.actor,
        actor_role=payload.actor_role,
        action=AuditAction.REQUIREMENT_VERSION_CREATED,
        entity_type=EntityType.REQUIREMENT_VERSION,
        entity_id=version.id,
        after=version_snapshot(version),
        trace_id=trace_id,
        detail={"requirement_id": str(requirement.id), "version": 1},
    )
    db.commit()
    return get_requirement(db, requirement.id)


def create_version(
    db: Session,
    requirement_id: uuid.UUID,
    payload: RequirementVersionCreate,
    *,
    trace_id: str | None,
) -> RequirementVersion:
    """Append an immutable new version and update the requirement status."""
    requirement = get_requirement(db, requirement_id)
    resolve_policy_refs(db, payload.policy_ids)

    latest = requirement.versions[-1] if requirement.versions else None
    if (
        latest is not None
        and latest.text == payload.text
        and sorted(latest.policy_ids) == sorted(payload.policy_ids)
    ):
        raise ConflictError(
            "The new version is identical to the latest version.",
            details={"latest_version": latest.version},
        )

    status_before = RequirementStatus(requirement.status)
    version = RequirementVersion(
        version=requirement.latest_version + 1,
        text=payload.text,
        policy_ids=list(payload.policy_ids),
        author=payload.actor,
        change_note=payload.change_note,
    )
    requirement.versions.append(version)
    requirement.status = _status_after_new_version(status_before)
    requirement.updated_at = utc_now()
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "Another version was created at the same time; retry.",
            details={"requirement_id": str(requirement_id)},
        ) from exc

    record_audit_event(
        db,
        actor=payload.actor,
        actor_role=payload.actor_role,
        action=AuditAction.REQUIREMENT_VERSION_CREATED,
        entity_type=EntityType.REQUIREMENT_VERSION,
        entity_id=version.id,
        after=version_snapshot(version),
        trace_id=trace_id,
        detail={
            "requirement_id": str(requirement.id),
            "version": version.version,
            "change_note": version.change_note,
            "requirement_status_before": status_before.value,
            "requirement_status_after": RequirementStatus(requirement.status).value,
        },
    )
    db.commit()
    return version
