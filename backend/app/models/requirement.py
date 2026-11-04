"""Requirement and requirement-version models."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.contracts import RequirementStatus
from app.database.base import Base, JSONList, TimestampMixin, UUIDPrimaryKeyMixin, enum_type, uuid_fk

if TYPE_CHECKING:
    from app.models.specification import Spec


class Requirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A product requirement identified by a human-readable code such as ``RQ-014``."""

    __tablename__ = "requirements"

    code: Mapped[str] = mapped_column(String(16), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[RequirementStatus] = mapped_column(
        enum_type(RequirementStatus, "requirement_status"),
        default=RequirementStatus.DRAFT,
        index=True,
    )

    versions: Mapped[list[RequirementVersion]] = relationship(
        back_populates="requirement",
        passive_deletes="all",
        order_by="RequirementVersion.version",
    )

    @property
    def latest_version(self) -> int:
        """Return the highest version number, or 0 if there are no versions yet."""
        return max((version.version for version in self.versions), default=0)


class RequirementVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An immutable version of a requirement's text and attached policy references."""

    __tablename__ = "requirement_versions"
    __table_args__ = (
        UniqueConstraint("requirement_id", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    requirement_id: Mapped[uuid.UUID] = uuid_fk("requirements.id", ondelete="RESTRICT")
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    policy_ids: Mapped[list[str]] = mapped_column(JSONList, default=list)
    author: Mapped[str] = mapped_column(String(80))
    change_note: Mapped[str | None] = mapped_column(String(500))

    requirement: Mapped[Requirement] = relationship(back_populates="versions")
    specs: Mapped[list[Spec]] = relationship(
        back_populates="requirement_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Spec.version",
    )
