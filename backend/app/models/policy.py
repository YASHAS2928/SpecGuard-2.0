"""Versioned, effective-dated policy registry (all policies are fictional)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Policy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One version of a policy, e.g. ``POL-OT-01`` version 1."""

    __tablename__ = "policies"
    __table_args__ = (
        UniqueConstraint("policy_code", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="effective_range",
        ),
    )

    policy_code: Mapped[str] = mapped_column(String(24), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    rule_text: Mapped[str] = mapped_column(Text)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    fictional: Mapped[bool] = mapped_column(Boolean, default=True)
    sha256: Mapped[str] = mapped_column(String(64))

    @property
    def ref(self) -> str:
        """Return the versioned reference, e.g. ``POL-OT-01@v1``."""
        return f"{self.policy_code}@v{self.version}"

    def is_effective_on(self, day: date) -> bool:
        """Return ``True`` if this policy version applies on ``day``."""
        return self.effective_from <= day and (self.effective_to is None or day <= self.effective_to)
