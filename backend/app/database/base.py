"""Declarative base, shared mixins and column helpers for SpecGuard models.

* Primary keys are UUIDs (stored by SQLAlchemy's ``Uuid`` type as 32-character
  hex text on SQLite, and returned to Python as ``uuid.UUID``).
* Enums are stored as their string values with a named CHECK constraint.
* JSON columns track top-level mutations (``MutableDict`` / ``MutableList``).
  Nested changes are not tracked: assign a new value instead of mutating deep
  structures in place.
* UUIDs inside JSON must be stored as strings (JSON has no UUID type).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, MetaData, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedColumn, mapped_column
from sqlalchemy.types import TypeDecorator

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_N_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

ENUM_LENGTH = 64

JSONDict = MutableDict.as_mutable(JSON)
JSONList = MutableList.as_mutable(JSON)


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """Store naive UTC timestamps and return aware UTC datetimes.

    Naive inputs are treated as UTC, including existing SQLite timestamps.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    """Declarative base with deterministic constraint names and type mappings."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        uuid.UUID: Uuid(as_uuid=True),
        datetime: UTCDateTime(),
    }


class UUIDPrimaryKeyMixin:
    """Adds a UUID primary key generated in Python (``uuid4``)."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    """Adds a ``created_at`` column for append-only records."""

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    """Adds ``created_at`` and ``updated_at`` columns maintained by the ORM.

    SQLite does not store timezone offsets; values are written as naive UTC and
    read back with ``timezone.utc`` attached.
    """

    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )


def enum_type(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Return a portable enum column type storing values with a named CHECK constraint."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=ENUM_LENGTH,
        values_callable=lambda members: [member.value for member in members],
    )


def uuid_fk(
    target: str,
    *,
    nullable: bool = False,
    ondelete: str = "CASCADE",
    index: bool = True,
) -> MappedColumn[Any]:
    """Return a UUID foreign-key column referencing ``target`` (``"table.column"``)."""
    return mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
        index=index,
    )
