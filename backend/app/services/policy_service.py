"""Policy registry queries: listing, effective-date filtering and reference resolution."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.contracts import ErrorCode
from app.core.errors import ApiError
from app.models import Policy

_POLICY_REF_RE = re.compile(r"^(POL-[A-Z]{2,10}-\d{2})@v(\d{1,3})$")


def utc_today() -> date:
    """Return today's date in UTC."""
    return datetime.now(timezone.utc).date()


def _invalid(message: str, details: dict[str, object]) -> ApiError:
    return ApiError(
        message,
        details=details,
        code=ErrorCode.VALIDATION_ERROR,
        status_code=422,
    )


def parse_policy_ref(ref: str) -> tuple[str, int]:
    """Split ``POL-OT-01@v1`` into ``("POL-OT-01", 1)``."""
    match = _POLICY_REF_RE.fullmatch(ref)
    if match is None:
        raise _invalid("Invalid policy reference.", {"policy_ref": ref})
    return match.group(1), int(match.group(2))


def list_policies(
    db: Session,
    *,
    effective_on: date | None = None,
    code: str | None = None,
    include_all_versions: bool = False,
) -> list[Policy]:
    """List policies ordered by code and version.

    By default only versions effective on ``effective_on`` (today in UTC if not
    given) are returned. ``include_all_versions`` ignores the date filter.
    """
    stmt = select(Policy)
    if code is not None:
        stmt = stmt.where(Policy.policy_code == code)
    if not include_all_versions:
        day = effective_on or utc_today()
        stmt = stmt.where(
            Policy.effective_from <= day,
            or_(Policy.effective_to.is_(None), Policy.effective_to >= day),
        )
    stmt = stmt.order_by(Policy.policy_code, Policy.version)
    return list(db.scalars(stmt))


def resolve_policy_refs(db: Session, refs: Sequence[str]) -> list[Policy]:
    """Return the policies for ``refs`` in the same order, or raise a 422 error.

    Rules: every reference must exist, and a requirement version may cite only
    one version of each policy. Effective-date checks happen during analysis
    (validation code V04), not here.
    """
    parsed = [parse_policy_ref(ref) for ref in refs]
    counts = Counter(code for code, _ in parsed)
    duplicated = sorted(code for code, count in counts.items() if count > 1)
    if duplicated:
        raise _invalid(
            "Cite only one version of each policy.", {"duplicate_policy_codes": duplicated}
        )

    candidates = db.scalars(select(Policy).where(Policy.policy_code.in_(list(counts)))).all()
    by_ref = {policy.ref: policy for policy in candidates}
    missing = [ref for ref in refs if ref not in by_ref]
    if missing:
        raise _invalid("Unknown policy reference(s).", {"unknown_policy_ids": missing})
    return [by_ref[ref] for ref in refs]
