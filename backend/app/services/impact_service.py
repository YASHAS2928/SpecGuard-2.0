"""Change impact between two specifications of the same requirement.

Scenarios are matched by fixture hash (inputs + assertion). With the same hash the test is
UNAFFECTED when its oracle expected value is unchanged and STALE_EXPECTED when it changed; an old
scenario that is no longer designed is OBSOLETE; a new scenario with no old counterpart is NEW.

Effects: approved STALE_EXPECTED tests become STALE and OBSOLETE tests become OBSOLETE (both leave
the runnable set). The new specification gets DRAFT tests (designed now unless it already has
tests) linked to the old ones through ``supersedes_id``. Humans re-approve them; nothing is
auto-approved. ``rerun_test_ids`` are the new tests that replace stale tests or are NEW.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.contracts import (
    AuditAction,
    ChangeImpactRequest,
    ChangeImpactResponse,
    EntityType,
    ExpectedResult,
    ImpactClass,
    ImpactedTest,
    SpecStatus,
    TestOrigin,
    TestStatus,
)
from app.core.errors import ConflictError, StateTransitionError
from app.core.state_machine import SPEC_EDITOR_ROLES, assert_test_transition, require_role
from app.engine.protocol import ExistingTest, QualityEngine
from app.models import ChangeImpact, TestCase, TraceLink, TraceLinkType
from app.services.engine_bridge import call_engine, engine_spec_for, load_spec
from app.services.test_service import build_test_responses, persist_design, test_snapshot


def _existing(test: TestCase) -> ExistingTest:
    return ExistingTest(str(test.id), test.tc_code, test.fixture_hash, dict(test.expected),
                        TestStatus(test.status).value, TestOrigin(test.origin).value)


def to_response(row: ChangeImpact, warnings: list[str] | None = None) -> ChangeImpactResponse:
    return ChangeImpactResponse.model_validate({
        "id": row.id, "from_spec_id": row.from_spec_id, "to_spec_id": row.to_spec_id,
        "rule_changes": row.rule_changes, "impacted_criteria": row.impacted_criteria,
        "impacted_tests": row.impacted_tests, "counts": row.counts,
        "rerun_test_ids": [uuid.UUID(i) for i in row.rerun_test_ids], "created_at": row.created_at,
        "warnings": warnings or []})


def analyze_impact(
    db: Session, new_spec_id: uuid.UUID, payload: ChangeImpactRequest, *, engine: QualityEngine,
    trace_id: str | None,
) -> ChangeImpactResponse:
    require_role(payload.actor_role, SPEC_EDITOR_ROLES, "analyse change impact")
    new = load_spec(db, new_spec_id)
    old = load_spec(db, payload.from_spec_id)
    if old.id == new.id:
        raise StateTransitionError("A specification cannot be compared with itself.",
                                   details={"spec_id": str(new.id)})
    if old.requirement_version.requirement_id != new.requirement_version.requirement_id:
        raise StateTransitionError("The specifications belong to different requirements.",
                                   details={"from_spec_id": str(old.id), "to_spec_id": str(new.id)})
    if new.status != SpecStatus.APPROVED or old.status not in (SpecStatus.APPROVED, SpecStatus.SUPERSEDED):
        raise StateTransitionError(
            "The new specification must be APPROVED and the earlier one APPROVED or SUPERSEDED.",
            details={"from_status": SpecStatus(old.status).value, "to_status": SpecStatus(new.status).value})
    if db.scalar(select(ChangeImpact.id).where(ChangeImpact.from_spec_id == old.id,
                                               ChangeImpact.to_spec_id == new.id)) is not None:
        raise ConflictError("Change impact was already analysed for these specifications.",
                            details={"from_spec_id": str(old.id), "to_spec_id": str(new.id)})

    old_engine, new_engine = engine_spec_for(db, old, engine), engine_spec_for(db, new, engine)
    rule_changes = call_engine(lambda: engine.classify_rules(old_engine, new_engine))

    new_tests = list(db.scalars(select(TestCase).where(TestCase.spec_id == new.id).order_by(TestCase.tc_code)))
    designed_now = not new_tests
    if designed_now:
        criteria = call_engine(lambda: engine.derive_criteria(new_engine))
        designed = call_engine(lambda: engine.design_tests(new_engine, []))
        new_tests = persist_design(db, new, designed, criteria)
    old_tests = list(db.scalars(select(TestCase).where(TestCase.spec_id == old.id).order_by(TestCase.tc_code)))
    by_id = {str(t.id): t for t in [*old_tests, *new_tests]}

    # Only runnable (non-blocked) tests of the new spec can be counterparts of old tests.
    runnable_new = [t for t in new_tests if t.status != TestStatus.BLOCKED]
    items = call_engine(lambda: engine.classify_tests([_existing(t) for t in old_tests],
                                                      [_existing(t) for t in runnable_new]))
    for item in items:
        old_test = by_id.get(item.old_id) if item.old_id else None
        new_test = by_id.get(item.new_key) if item.new_key else None
        if old_test is not None and new_test is not None and new_test.supersedes_id is None:
            new_test.supersedes_id = old_test.id
            db.add(TraceLink(spec_id=new.id, from_type=EntityType.TEST_CASE, from_id=new_test.id,
                             to_type=EntityType.TEST_CASE, to_id=old_test.id, link_type=TraceLinkType.SUPERSEDES))
        if old_test is None:
            continue
        status = TestStatus(old_test.status)
        if item.impact_class == ImpactClass.STALE_EXPECTED.value and status == TestStatus.APPROVED:
            assert_test_transition(status, TestStatus.STALE)
            old_test.status = TestStatus.STALE
        elif item.impact_class == ImpactClass.OBSOLETE.value:
            assert_test_transition(status, TestStatus.OBSOLETE)
            old_test.status = TestStatus.OBSOLETE
    db.flush()

    responses = {str(r.id): r for r in build_test_responses(db, [*old_tests, *new_tests])}
    impacted: list[ImpactedTest] = []
    criteria_codes: set[str] = set()
    rerun: list[uuid.UUID] = []
    counts: dict[str, int] = {c.value: 0 for c in ImpactClass}
    for item in items:
        counts[item.impact_class] += 1
        subject = responses[item.old_id or item.new_key or ""]
        if item.impact_class != ImpactClass.UNAFFECTED.value:
            criteria_codes.update(subject.criterion_codes)
        replacement = by_id[item.new_key] if item.new_key else None
        if item.impact_class in (ImpactClass.STALE_EXPECTED.value, ImpactClass.NEW.value) and replacement is not None \
                and replacement.status != TestStatus.BLOCKED and replacement.id not in rerun:
            rerun.append(replacement.id)
        impacted.append(ImpactedTest(
            test_id=subject.id, tc_code=subject.tc_code, impact_class=ImpactClass(item.impact_class),
            reason=item.reason, old_expected=ExpectedResult.model_validate(item.old_expected) if item.old_expected else None,
            new_expected=ExpectedResult.model_validate(item.new_expected) if item.new_expected else None,
            replacement_test_id=replacement.id if item.impact_class == ImpactClass.STALE_EXPECTED.value and replacement else None))

    warnings: list[str] = []
    if designed_now:
        warnings.append(
            "Tests were designed for the new specification during this analysis, without AI edge cases. "
            "Run design-tests (with AI if wanted) on the new specification before impact analysis.")
        lost = sum(1 for item in items if item.impact_class == ImpactClass.OBSOLETE.value
                   and item.old_id and by_id[item.old_id].origin == TestOrigin.AI)
        if lost:
            warnings.append(f"{lost} AI-origin test(s) of the earlier specification were marked OBSOLETE "
                            "because the new specification has no AI tests yet.")
    row = ChangeImpact(
        from_spec_id=old.id, to_spec_id=new.id, rule_changes=[c.model_dump(mode="json") for c in rule_changes],
        impacted_criteria=sorted(criteria_codes), impacted_tests=[t.model_dump(mode="json") for t in impacted],
        counts=counts, rerun_test_ids=[str(i) for i in rerun], actor=payload.actor)
    db.add(row)
    db.flush()
    record_audit_event(
        db, actor=payload.actor, actor_role=payload.actor_role, action=AuditAction.CHANGE_IMPACT_ANALYZED,
        entity_type=EntityType.CHANGE_IMPACT, entity_id=row.id,
        after={"id": str(row.id), "counts": counts, "rerun": len(rerun)}, trace_id=trace_id,
        detail={"from_spec_id": str(old.id), "to_spec_id": str(new.id), "counts": counts,
                "rule_changes": len(rule_changes)})
    db.commit()
    return to_response(row, warnings)
