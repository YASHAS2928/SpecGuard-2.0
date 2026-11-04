"""LLM call log, append-only audit events and evaluation runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, Index, Integer, String, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.core.contracts import ActorRole, AIProvider, AuditAction, EntityType
from app.database.base import (
    Base,
    CreatedAtMixin,
    JSONDict,
    UUIDPrimaryKeyMixin,
    enum_type,
    utc_now,
)


class LlmStage(StrEnum):
    """Pipeline stages that may call an LLM."""

    EXTRACTION = "EXTRACTION"
    CLARIFICATION = "CLARIFICATION"
    EDGE_CASES = "EDGE_CASES"
    HYPOTHESIS = "HYPOTHESIS"


class AuditImmutableError(RuntimeError):
    """Raised when code tries to update or delete an audit event."""


class LlmCall(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Metadata about one AI provider call. Never stores keys or raw prompts."""

    __tablename__ = "llm_calls"
    __table_args__ = (Index("ix_llm_calls_stage_created_at", "stage", "created_at"),)

    stage: Mapped[LlmStage] = mapped_column(enum_type(LlmStage, "llm_stage"))
    provider: Mapped[AIProvider] = mapped_column(enum_type(AIProvider, "llm_provider"))
    model: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(32))
    input_hash: Mapped[str] = mapped_column(String(64))
    output_hash: Mapped[str | None] = mapped_column(String(64))
    valid_first_try: Mapped[bool] = mapped_column(Boolean, default=False)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(64))


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    """An append-only audit record. Updates and deletes are refused by the ORM."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_entity", "entity_type", "entity_id"),)

    ts: Mapped[datetime] = mapped_column(default=utc_now, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    actor_role: Mapped[ActorRole] = mapped_column(enum_type(ActorRole, "audit_actor_role"))
    action: Mapped[AuditAction] = mapped_column(enum_type(AuditAction, "audit_action"), index=True)
    entity_type: Mapped[EntityType] = mapped_column(enum_type(EntityType, "audit_entity_type"))
    entity_id: Mapped[uuid.UUID] = mapped_column()
    before_hash: Mapped[str | None] = mapped_column(String(64))
    after_hash: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONDict)


@event.listens_for(AuditEvent, "before_update")
def _refuse_audit_update(_mapper: Mapper[Any], _connection: Any, target: AuditEvent) -> None:
    raise AuditImmutableError(f"Audit event {target.id} is append-only and cannot be updated.")


@event.listens_for(AuditEvent, "before_delete")
def _refuse_audit_delete(_mapper: Mapper[Any], _connection: Any, target: AuditEvent) -> None:
    raise AuditImmutableError(f"Audit event {target.id} is append-only and cannot be deleted.")


class EvalRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One evaluation run with measured metrics (never hand-entered)."""

    __tablename__ = "eval_runs"

    provider: Mapped[AIProvider] = mapped_column(enum_type(AIProvider, "eval_provider"))
    model: Mapped[str | None] = mapped_column(String(120))
    prompt_versions: Mapped[dict[str, Any]] = mapped_column(JSONDict, default=dict)
    git_sha: Mapped[str | None] = mapped_column(String(40))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONDict, default=dict)
    notes: Mapped[str | None] = mapped_column(String(500))
