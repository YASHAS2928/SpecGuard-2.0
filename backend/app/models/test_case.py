"""Test case, traceability link, validation issue and review models."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.contracts import (
    ActorRole,
    AssertionTemplate,
    EntityType,
    IssueSeverity,
    ReviewDecision,
    TestOrigin,
    TestStatus,
    TestTechnique,
    ValidationCode,
)
from app.database.base import (
    Base,
    CreatedAtMixin,
    JSONDict,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
    uuid_fk,
)

if TYPE_CHECKING:
    from app.models.specification import Spec


class TraceLinkType(StrEnum):
    """Kinds of edges in the requirement-to-defect traceability graph."""

    DERIVED_FROM = "DERIVED_FROM"
    VERIFIES = "VERIFIES"
    COVERS = "COVERS"
    CITES = "CITES"
    PRODUCED_BY = "PRODUCED_BY"
    EVIDENCES = "EVIDENCES"
    SUPERSEDES = "SUPERSEDES"


class TestCase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An executable test. Expected values are set by the deterministic oracle only."""

    __test__ = False

    __tablename__ = "test_cases"
    __table_args__ = (
        UniqueConstraint("spec_id", "tc_code"),
        CheckConstraint(
            "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 20)",
            name="risk_score_range",
        ),
        Index("ix_test_cases_spec_id_status", "spec_id", "status"),
    )

    spec_id: Mapped[uuid.UUID] = uuid_fk("specs.id")
    tc_code: Mapped[str] = mapped_column(String(8))
    origin: Mapped[TestOrigin] = mapped_column(enum_type(TestOrigin, "test_origin"))
    technique: Mapped[TestTechnique] = mapped_column(enum_type(TestTechnique, "test_technique"))
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONDict, default=dict)
    fixture_hash: Mapped[str] = mapped_column(String(64), index=True)
    assertion: Mapped[AssertionTemplate] = mapped_column(
        enum_type(AssertionTemplate, "assertion_template")
    )
    expected: Mapped[dict[str, Any]] = mapped_column(JSONDict, default=dict)
    ai_claimed_expected: Mapped[dict[str, Any] | None] = mapped_column(JSONDict)
    rationale: Mapped[str] = mapped_column(String(500), default="")
    risk_score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[TestStatus] = mapped_column(
        enum_type(TestStatus, "test_status"), default=TestStatus.DRAFT
    )
    supersedes_id: Mapped[uuid.UUID | None] = uuid_fk(
        "test_cases.id", nullable=True, ondelete="SET NULL"
    )

    spec: Mapped[Spec] = relationship(back_populates="test_cases", foreign_keys=[spec_id])


class TraceLink(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A directed edge between two traceable entities.

    The endpoints are polymorphic (entity type + UUID), so they cannot be
    foreign keys. ``spec_id`` scopes the link so it is deleted with its spec.
    """

    __tablename__ = "trace_links"
    __table_args__ = (
        UniqueConstraint("from_type", "from_id", "to_type", "to_id", "link_type"),
        Index("ix_trace_links_from", "from_type", "from_id"),
        Index("ix_trace_links_to", "to_type", "to_id"),
    )

    spec_id: Mapped[uuid.UUID | None] = uuid_fk("specs.id", nullable=True)
    from_type: Mapped[EntityType] = mapped_column(enum_type(EntityType, "trace_from_type"))
    from_id: Mapped[uuid.UUID] = mapped_column()
    to_type: Mapped[EntityType] = mapped_column(enum_type(EntityType, "trace_to_type"))
    to_id: Mapped[uuid.UUID] = mapped_column()
    link_type: Mapped[TraceLinkType] = mapped_column(enum_type(TraceLinkType, "trace_link_type"))


class ValidationIssueRecord(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A stored validation finding. Re-validation deactivates old findings."""

    __tablename__ = "validation_issues"
    __table_args__ = (
        Index("ix_validation_issues_entity", "entity_type", "entity_id"),
        Index("ix_validation_issues_spec_active_severity", "spec_id", "active", "severity"),
    )

    spec_id: Mapped[uuid.UUID | None] = uuid_fk("specs.id", nullable=True, index=False)
    entity_type: Mapped[EntityType] = mapped_column(enum_type(EntityType, "issue_entity_type"))
    entity_id: Mapped[uuid.UUID] = mapped_column()
    code: Mapped[ValidationCode] = mapped_column(enum_type(ValidationCode, "validation_code"))
    severity: Mapped[IssueSeverity] = mapped_column(enum_type(IssueSeverity, "issue_severity"))
    message: Mapped[str] = mapped_column(String(500))
    field_path: Mapped[str | None] = mapped_column(String(200))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONDict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Review(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A human review decision on a test case or specification."""

    __tablename__ = "reviews"
    __table_args__ = (Index("ix_reviews_entity", "entity_type", "entity_id"),)

    entity_type: Mapped[EntityType] = mapped_column(enum_type(EntityType, "review_entity_type"))
    entity_id: Mapped[uuid.UUID] = mapped_column()
    decision: Mapped[ReviewDecision] = mapped_column(enum_type(ReviewDecision, "review_decision"))
    reviewer: Mapped[str] = mapped_column(String(80))
    reviewer_role: Mapped[ActorRole] = mapped_column(enum_type(ActorRole, "reviewer_role"))
    reason: Mapped[str | None] = mapped_column(String(500))
