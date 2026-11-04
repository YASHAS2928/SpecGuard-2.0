"""System-under-test versions, runs, results, defects and change impacts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.contracts import DefectStatus, ResultStatus, RunStatus, RunTrigger
from app.database.base import (
    Base,
    CreatedAtMixin,
    JSONDict,
    JSONList,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
    utc_now,
    uuid_fk,
)

if TYPE_CHECKING:
    from app.models.specification import Spec
    from app.models.test_case import TestCase


class SutVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A known version of the mock Time-to-Pay API (system under test)."""

    __tablename__ = "sut_versions"
    __table_args__ = (UniqueConstraint("name", "version"),)

    name: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(String(500))


class Run(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One execution of approved tests against the system under test."""

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "passed >= 0 AND failed >= 0 AND errors >= 0 AND passed + failed + errors <= total",
            name="totals_consistent",
        ),
        Index("ix_runs_spec_id_started_at", "spec_id", "started_at"),
    )

    spec_id: Mapped[uuid.UUID] = uuid_fk("specs.id", index=False)
    sut_version: Mapped[str] = mapped_column(String(32))
    sut_version_id: Mapped[uuid.UUID | None] = uuid_fk(
        "sut_versions.id", nullable=True, ondelete="SET NULL"
    )
    trigger: Mapped[RunTrigger] = mapped_column(enum_type(RunTrigger, "run_trigger"))
    status: Mapped[RunStatus] = mapped_column(
        enum_type(RunStatus, "run_status"), default=RunStatus.PENDING
    )
    actor: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column()
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)

    spec: Mapped[Spec] = relationship()
    results: Mapped[list[Result]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class Result(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The outcome of one test case in one run."""

    __tablename__ = "results"
    __table_args__ = (UniqueConstraint("run_id", "test_case_id"),)

    run_id: Mapped[uuid.UUID] = uuid_fk("runs.id")
    test_case_id: Mapped[uuid.UUID] = uuid_fk("test_cases.id")
    status: Mapped[ResultStatus] = mapped_column(
        enum_type(ResultStatus, "result_status"), index=True
    )
    expected: Mapped[dict[str, Any]] = mapped_column(JSONDict, default=dict)
    observed: Mapped[dict[str, Any] | None] = mapped_column(JSONDict)
    failed_assertion: Mapped[str | None] = mapped_column(String(300))
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    run: Mapped[Run] = relationship(back_populates="results")
    test_case: Mapped[TestCase] = relationship()


class Defect(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A cluster of related failures. ``evidence_result_ids`` holds UUID strings."""

    __tablename__ = "defects"
    __table_args__ = (UniqueConstraint("spec_id", "cluster_key"),)

    spec_id: Mapped[uuid.UUID] = uuid_fk("specs.id", index=False)
    cluster_key: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    rule_key: Mapped[str | None] = mapped_column(String(41))
    partition: Mapped[dict[str, Any]] = mapped_column(JSONDict, default=dict)
    status: Mapped[DefectStatus] = mapped_column(
        enum_type(DefectStatus, "defect_status"), default=DefectStatus.OPEN, index=True
    )
    first_run_id: Mapped[uuid.UUID] = uuid_fk("runs.id")
    last_run_id: Mapped[uuid.UUID | None] = uuid_fk("runs.id", nullable=True, ondelete="SET NULL")
    evidence_result_ids: Mapped[list[str]] = mapped_column(JSONList, default=list)
    hypothesis: Mapped[dict[str, Any] | None] = mapped_column(JSONDict)

    first_run: Mapped[Run] = relationship(foreign_keys=[first_run_id])


class ChangeImpact(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A stored change-impact report between two approved specs.

    ``rerun_test_ids`` and IDs inside ``impacted_tests`` are UUID strings.
    """

    __tablename__ = "change_impacts"
    __table_args__ = (
        CheckConstraint("from_spec_id <> to_spec_id", name="different_specs"),
    )

    from_spec_id: Mapped[uuid.UUID] = uuid_fk("specs.id")
    to_spec_id: Mapped[uuid.UUID] = uuid_fk("specs.id")
    rule_changes: Mapped[list[Any]] = mapped_column(JSONList, default=list)
    impacted_criteria: Mapped[list[str]] = mapped_column(JSONList, default=list)
    impacted_tests: Mapped[list[Any]] = mapped_column(JSONList, default=list)
    counts: Mapped[dict[str, Any]] = mapped_column(JSONDict, default=dict)
    rerun_test_ids: Mapped[list[str]] = mapped_column(JSONList, default=list)
    actor: Mapped[str] = mapped_column(String(80))
