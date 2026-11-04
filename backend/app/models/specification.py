"""Specification, extracted rule, ambiguity and acceptance-criterion models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.contracts import AmbiguityStatus, RuleOrigin, RuleType, SpecStatus
from app.database.base import (
    Base,
    JSONDict,
    JSONList,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
    uuid_fk,
)

if TYPE_CHECKING:
    from app.models.requirement import RequirementVersion
    from app.models.test_case import TestCase


class Spec(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An executable specification derived from one requirement version."""

    __tablename__ = "specs"
    __table_args__ = (
        UniqueConstraint("requirement_version_id", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    requirement_version_id: Mapped[uuid.UUID] = uuid_fk("requirement_versions.id")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[SpecStatus] = mapped_column(
        enum_type(SpecStatus, "spec_status"), default=SpecStatus.DRAFT, index=True
    )
    inputs: Mapped[list[Any]] = mapped_column(JSONList, default=list)
    outputs: Mapped[list[Any]] = mapped_column(JSONList, default=list)
    assumptions: Mapped[list[Any]] = mapped_column(JSONList, default=list)
    parent_spec_id: Mapped[uuid.UUID | None] = uuid_fk(
        "specs.id", nullable=True, ondelete="SET NULL"
    )
    analysis_llm_call_id: Mapped[uuid.UUID | None] = uuid_fk(
        "llm_calls.id", nullable=True, ondelete="SET NULL"
    )
    approved_by: Mapped[str | None] = mapped_column(String(80))
    approved_at: Mapped[datetime | None] = mapped_column()

    requirement_version: Mapped[RequirementVersion] = relationship(back_populates="specs")
    parent: Mapped[Spec | None] = relationship(
        remote_side="Spec.id", foreign_keys="Spec.parent_spec_id"
    )
    rules: Mapped[list[SpecRule]] = relationship(
        back_populates="spec",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SpecRule.rule_key",
    )
    ambiguities: Mapped[list[AmbiguityRecord]] = relationship(
        back_populates="spec",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AmbiguityRecord.amb_code",
    )
    criteria: Mapped[list[Criterion]] = relationship(
        back_populates="spec",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Criterion.crit_code",
    )
    test_cases: Mapped[list[TestCase]] = relationship(
        back_populates="spec",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TestCase.tc_code",
        foreign_keys="TestCase.spec_id",
    )


class SpecRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A typed business rule inside a specification, with its grounded source span."""

    __tablename__ = "spec_rules"
    __table_args__ = (UniqueConstraint("spec_id", "rule_key"),)

    spec_id: Mapped[uuid.UUID] = uuid_fk("specs.id")
    rule_key: Mapped[str] = mapped_column(String(41))
    type: Mapped[RuleType] = mapped_column(enum_type(RuleType, "rule_type"))
    params: Mapped[dict[str, Any]] = mapped_column(JSONDict, default=dict)
    origin: Mapped[RuleOrigin] = mapped_column(enum_type(RuleOrigin, "rule_origin"))
    policy_ref: Mapped[str | None] = mapped_column(String(32))
    source_span: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(String(200))
    grounded: Mapped[bool | None] = mapped_column(Boolean)

    spec: Mapped[Spec] = relationship(back_populates="rules")


class AmbiguityRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A clarification question with option patches, resolved by a human."""

    __tablename__ = "ambiguities"
    __table_args__ = (
        UniqueConstraint("spec_id", "amb_code"),
        CheckConstraint(
            "chosen_option_index IS NULL OR (chosen_option_index >= 0 AND chosen_option_index <= 3)",
            name="option_index_range",
        ),
    )

    spec_id: Mapped[uuid.UUID] = uuid_fk("specs.id")
    amb_code: Mapped[str] = mapped_column(String(8))
    question: Mapped[str] = mapped_column(String(300))
    why: Mapped[str] = mapped_column(String(500))
    affects_rules: Mapped[list[str]] = mapped_column(JSONList, default=list)
    options: Mapped[list[Any]] = mapped_column(JSONList, default=list)
    status: Mapped[AmbiguityStatus] = mapped_column(
        enum_type(AmbiguityStatus, "ambiguity_status"),
        default=AmbiguityStatus.OPEN,
        index=True,
    )
    chosen_option_index: Mapped[int | None] = mapped_column(Integer)
    resolved_by: Mapped[str | None] = mapped_column(String(80))
    resolved_at: Mapped[datetime | None] = mapped_column()
    comment: Mapped[str | None] = mapped_column(String(500))

    spec: Mapped[Spec] = relationship(back_populates="ambiguities")


class Criterion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Given/When/Then acceptance criterion derived from one rule."""

    __tablename__ = "criteria"
    __table_args__ = (UniqueConstraint("spec_id", "crit_code"),)

    spec_id: Mapped[uuid.UUID] = uuid_fk("specs.id")
    crit_code: Mapped[str] = mapped_column(String(8))
    rule_key: Mapped[str] = mapped_column(String(41))
    given_text: Mapped[str] = mapped_column(Text)
    when_text: Mapped[str] = mapped_column(Text)
    then_text: Mapped[str] = mapped_column(Text)

    spec: Mapped[Spec] = relationship(back_populates="criteria")
