"""Idempotent seed of fictional reference data.

Creates the fictional policy registry and the known mock Time-to-Pay API
versions. Existing rows are left untouched. A policy version is immutable:
if a seeded policy already exists with different content, seeding stops with
``SeedConflictError`` instead of silently changing history.

Run from the ``backend`` directory:

    python -m app.database.seed
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.init_db import init_db
from app.database.session import session_scope
from app.models import Policy, SutVersion

logger = logging.getLogger("specguard.seed")


class SeedConflictError(RuntimeError):
    """Raised when existing reference data differs from the seed definition."""


@dataclass(frozen=True)
class PolicySeed:
    policy_code: str
    version: int
    title: str
    rule_text: str
    effective_from: date
    effective_to: date | None


@dataclass(frozen=True)
class SutVersionSeed:
    name: str
    version: str
    notes: str


@dataclass
class SeedReport:
    policies_created: int = 0
    policies_existing: int = 0
    sut_versions_created: int = 0
    sut_versions_existing: int = 0


FICTIONAL_POLICIES: tuple[PolicySeed, ...] = (
    PolicySeed(
        policy_code="POL-OT-01",
        version=1,
        title="Overtime threshold (fictional)",
        rule_text="For this mock business only: paid minutes above 480 in a single shift are overtime.",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    ),
    PolicySeed(
        policy_code="POL-OT-01",
        version=2,
        title="Overtime threshold, revised (fictional)",
        rule_text="For this mock business only: paid minutes above 450 in a single shift are overtime.",
        effective_from=date(2027, 1, 1),
        effective_to=None,
    ),
    PolicySeed(
        policy_code="POL-MEAL-02",
        version=1,
        title="Unpaid meal break deduction (fictional)",
        rule_text="Subtract a 30-minute unpaid meal break when an approved break event is present.",
        effective_from=date(2026, 1, 1),
        effective_to=None,
    ),
    PolicySeed(
        policy_code="POL-DATE-03",
        version=1,
        title="Overnight shift attribution (fictional)",
        rule_text="A shift crossing midnight belongs to the same shift instance, not two daily shifts.",
        effective_from=date(2026, 1, 1),
        effective_to=None,
    ),
)

SUT_VERSIONS: tuple[SutVersionSeed, ...] = (
    SutVersionSeed(
        name="mock-time-to-pay",
        version="1.3.0",
        notes="Seeded defect OVERNIGHT_WRAP: the overnight flag is ignored.",
    ),
    SutVersionSeed(
        name="mock-time-to-pay",
        version="1.4.0",
        notes="Overnight defect fixed.",
    ),
)


def policy_text_hash(rule_text: str) -> str:
    """Return the SHA-256 of a policy's rule text."""
    return hashlib.sha256(rule_text.encode("utf-8")).hexdigest()


def _seed_policy(db: Session, seed: PolicySeed, report: SeedReport) -> None:
    existing = db.scalar(
        select(Policy).where(Policy.policy_code == seed.policy_code, Policy.version == seed.version)
    )
    expected_hash = policy_text_hash(seed.rule_text)
    if existing is None:
        db.add(
            Policy(
                policy_code=seed.policy_code,
                version=seed.version,
                title=seed.title,
                rule_text=seed.rule_text,
                effective_from=seed.effective_from,
                effective_to=seed.effective_to,
                fictional=True,
                sha256=expected_hash,
            )
        )
        report.policies_created += 1
        return

    differs = (
        existing.sha256 != expected_hash
        or existing.rule_text != seed.rule_text
        or existing.effective_from != seed.effective_from
        or existing.effective_to != seed.effective_to
    )
    if differs:
        raise SeedConflictError(
            f"Policy {seed.policy_code}@v{seed.version} already exists with different content. "
            "Policy versions are immutable: add a new version instead of editing this one."
        )
    report.policies_existing += 1


def _seed_sut_version(db: Session, seed: SutVersionSeed, report: SeedReport) -> None:
    existing = db.scalar(
        select(SutVersion).where(SutVersion.name == seed.name, SutVersion.version == seed.version)
    )
    if existing is None:
        db.add(SutVersion(name=seed.name, version=seed.version, notes=seed.notes))
        report.sut_versions_created += 1
    else:
        report.sut_versions_existing += 1


def seed_reference_data(db: Session) -> SeedReport:
    """Insert missing reference data. Safe to run repeatedly; the caller commits."""
    report = SeedReport()
    for policy_seed in FICTIONAL_POLICIES:
        _seed_policy(db, policy_seed, report)
    for sut_seed in SUT_VERSIONS:
        _seed_sut_version(db, sut_seed, report)
    db.flush()
    return report


def main() -> None:
    """Command-line entry point: create tables if needed, then seed."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    init_db()
    with session_scope() as session:
        report = seed_reference_data(session)
    print(
        f"Policies: {report.policies_created} created, {report.policies_existing} already present. "
        f"SUT versions: {report.sut_versions_created} created, "
        f"{report.sut_versions_existing} already present."
    )


if __name__ == "__main__":
    main()
