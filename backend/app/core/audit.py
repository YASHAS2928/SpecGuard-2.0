"""Audit logging with deterministic hashing.

Snapshots are serialised as canonical JSON (sorted keys, compact separators,
UTC timestamps, UUIDs as strings) and hashed with SHA-256, so the same state
always produces the same hash. Audit events are append-only (see
``app.models.audit``). ``record_audit_event`` adds the event to the caller's
transaction; the caller commits.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.contracts import ActorRole, AuditAction, EntityType
from app.models.audit import AuditEvent

SYSTEM_ACTOR = "specguard-system"
_MAX_TRACE_ID_LENGTH = 64


def _json_default(value: Any) -> Any:
    """Convert non-JSON types to canonical JSON-safe values."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    raise TypeError(f"Cannot serialise value of type {type(value).__name__} for audit hashing.")


def canonical_json(data: Any) -> str:
    """Serialise ``data`` deterministically (sorted keys, no extra whitespace)."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )


def sha256_hex(data: Any) -> str | None:
    """Return the SHA-256 of ``data``'s canonical JSON, or ``None`` for ``None``."""
    if data is None:
        return None
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def to_json_safe(data: Any) -> Any:
    """Return ``data`` converted to plain JSON types (for storing in JSON columns)."""
    if data is None:
        return None
    return json.loads(canonical_json(data))


def record_audit_event(
    db: Session,
    *,
    actor: str,
    actor_role: ActorRole,
    action: AuditAction,
    entity_type: EntityType,
    entity_id: uuid.UUID,
    before: Any = None,
    after: Any = None,
    trace_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    """Add an audit event to the current transaction and flush it.

    ``before`` and ``after`` are state snapshots; only their hashes are stored.
    ``detail`` is stored as JSON and must not contain secrets.
    """
    event = AuditEvent(
        actor=actor,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_hash=sha256_hex(before),
        after_hash=sha256_hex(after),
        trace_id=trace_id[:_MAX_TRACE_ID_LENGTH] if trace_id else None,
        detail=to_json_safe(detail),
    )
    db.add(event)
    db.flush()
    return event
