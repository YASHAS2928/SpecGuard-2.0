"""Dashboard metrics and the audit trail, computed from database rows only."""

from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.contracts import (
    AuditAction,
    AuditEventResponse,
    AuditPage,
    AmbiguityStatus,
    DefectStatus,
    EntityType,
    IssueSeverity,
    MetricsOverviewResponse,
    ResultStatus,
    RunSummary,
    RunTotals,
    SpecStatus,
    TestStatus,
    ValidationCode,
)
from app.database.base import utc_now
from app.models import (
    AmbiguityRecord,
    AuditEvent,
    Defect,
    LlmCall,
    Requirement,
    Result,
    Run,
    Spec,
    SpecRule,
    TestCase,
    TraceLink,
    TraceLinkType,
    ValidationIssueRecord,
)


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def overview(db: Session) -> MetricsOverviewResponse:
    def count(model: type, *conditions: object) -> int:
        return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0

    ambiguities_total = count(AmbiguityRecord)
    ambiguities_resolved = count(AmbiguityRecord, AmbiguityRecord.status == AmbiguityStatus.RESOLVED)

    approved_rule_ids = set(db.scalars(
        select(SpecRule.id).join(Spec, SpecRule.spec_id == Spec.id).where(Spec.status == SpecStatus.APPROVED)))
    approved_test_ids = set(db.scalars(select(TestCase.id).where(TestCase.status == TestStatus.APPROVED)))
    latest: dict[uuid.UUID, ResultStatus] = {}
    for test_id, status in db.execute(select(Result.test_case_id, Result.status).order_by(Result.created_at, Result.id)):
        latest[test_id] = ResultStatus(status)
    passing_rules = {
        link.to_id for link in db.scalars(select(TraceLink).where(
            TraceLink.from_type == EntityType.TEST_CASE, TraceLink.link_type == TraceLinkType.VERIFIES))
        if link.to_id in approved_rule_ids and link.from_id in approved_test_ids
        and latest.get(link.from_id) == ResultStatus.PASS
    }

    by_status = Counter(TestStatus(s).value for s in db.scalars(select(TestCase.status)))
    blocks = Counter(ValidationCode(c).value for c in db.scalars(
        select(ValidationIssueRecord.code).where(ValidationIssueRecord.active.is_(True),
                                                 ValidationIssueRecord.severity == IssueSeverity.BLOCK)))
    last = db.scalars(select(Run).order_by(Run.started_at.desc(), Run.id).limit(1)).first()
    return MetricsOverviewResponse(
        requirements_total=count(Requirement),
        specs_approved=count(Spec, Spec.status == SpecStatus.APPROVED),
        ambiguities_total=ambiguities_total, ambiguities_resolved=ambiguities_resolved,
        requirement_completeness=_ratio(ambiguities_resolved, ambiguities_total),
        rules_total=len(approved_rule_ids), rules_with_passing_test=len(passing_rules),
        rule_coverage=_ratio(len(passing_rules), len(approved_rule_ids)),
        tests_by_status={s.value: by_status.get(s.value, 0) for s in TestStatus},
        validation_blocks_by_code=dict(sorted(blocks.items())),
        last_run=None if last is None else RunSummary(
            run_id=last.id, sut_version=last.sut_version, finished_at=last.finished_at,
            totals=RunTotals(total=last.total, passed=last.passed, failed=last.failed, errors=last.errors)),
        open_defects=count(Defect, Defect.status == DefectStatus.OPEN),
        tests_impacted_pending=count(TestCase, TestCase.status == TestStatus.STALE),
        ai_calls_total=count(LlmCall), ai_fallbacks_total=count(LlmCall, LlmCall.fallback.is_(True)),
        generated_at=utc_now(),
    )


def list_audit(
    db: Session, *, entity_type: EntityType | None, entity_id: uuid.UUID | None,
    action: AuditAction | None, limit: int, offset: int,
) -> AuditPage:
    conditions = []
    if entity_type is not None:
        conditions.append(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        conditions.append(AuditEvent.entity_id == entity_id)
    if action is not None:
        conditions.append(AuditEvent.action == action)
    total = db.scalar(select(func.count()).select_from(AuditEvent).where(*conditions)) or 0
    rows = db.scalars(select(AuditEvent).where(*conditions).order_by(AuditEvent.ts.desc(), AuditEvent.id)
                      .limit(limit).offset(offset))
    return AuditPage(
        items=[AuditEventResponse(
            id=e.id, ts=e.ts, actor=e.actor, actor_role=e.actor_role, action=e.action, entity_type=e.entity_type,
            entity_id=e.entity_id, before_hash=e.before_hash, after_hash=e.after_hash, trace_id=e.trace_id,
            detail=dict(e.detail) if e.detail else None) for e in rows],
        total=total, limit=limit, offset=offset)
