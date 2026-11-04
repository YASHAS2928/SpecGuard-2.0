"""Test design, listing and human review.

Safety rules enforced here:

* Only APPROVED specifications can have tests designed.
* Expected values come from the engine's oracle; AI output contributes inputs and a claim
  (stored separately). A test with any BLOCK issue is stored BLOCKED and can never be approved.
* AI-origin tests are approved one at a time; bulk approval refuses them.
* Everything (criteria, tests, issues, trace links, audit) is written in one transaction.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai.integration_interface import RequirementAI
from app.core.audit import record_audit_event, sha256_hex
from app.core.contracts import (
    AuditAction,
    CriterionResponse,
    DesignTestsRequest,
    DesignTestsResponse,
    EntityType,
    ErrorCode,
    ExpectedResult,
    IssueSeverity,
    ReviewDecision,
    SpecStatus,
    TestCaseResponse,
    TestOrigin,
    TestReviewItem,
    TestReviewRefusal,
    TestReviewRequest,
    TestReviewResponse,
    TestStatus,
    TestTechnique,
    ValidationCode,
    ValidationIssue,
)
from app.core.errors import NotFoundError, StateTransitionError
from app.core.state_machine import SPEC_EDITOR_ROLES, assert_test_transition, require_role
from app.database.base import utc_now
from app.engine.protocol import DesignedTest, DesignResult, QualityEngine
from app.models import (
    Criterion,
    LlmCall,
    LlmStage,
    Review,
    Spec,
    SpecRule,
    TestCase,
    TraceLink,
    TraceLinkType,
    ValidationIssueRecord,
)
from app.services.engine_bridge import call_engine, engine_spec_for, load_spec
from app.services.spec_service import build_spec_response, spec_snapshot

AI_UNAVAILABLE_MESSAGE = "AI edge cases are unavailable; the engine tests are complete."


def test_snapshot(test: TestCase) -> dict[str, Any]:
    return {
        "id": str(test.id), "tc_code": test.tc_code, "status": TestStatus(test.status).value,
        "fixture_hash": test.fixture_hash, "expected": dict(test.expected),
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def persist_design(
    db: Session, spec: Spec, result: DesignResult, criteria: Sequence[Any]
) -> list[TestCase]:
    """Store criteria, tests, issues and trace links for ``spec``. The caller commits."""
    rules = {rule.rule_key: rule for rule in spec.rules}
    criterion_rows: dict[str, Criterion] = {
        c.crit_code: c for c in db.scalars(select(Criterion).where(Criterion.spec_id == spec.id))
    }
    new_criteria: list[Criterion] = []
    for draft in criteria:
        if draft.code in criterion_rows:
            continue  # re-running design keeps the criteria that already exist
        row = Criterion(spec_id=spec.id, crit_code=draft.code, rule_key=draft.rule_key,
                        given_text=draft.given, when_text=draft.when, then_text=draft.then)
        criterion_rows[draft.code] = row
        new_criteria.append(row)
        db.add(row)
    db.flush()
    for row in new_criteria:
        db.add(TraceLink(spec_id=spec.id, from_type=EntityType.CRITERION, from_id=row.id,
                         to_type=EntityType.RULE, to_id=rules[row.rule_key].id,
                         link_type=TraceLinkType.DERIVED_FROM))

    start = db.scalars(select(TestCase.tc_code).where(TestCase.spec_id == spec.id)).all()
    counter = max((int(code.split("-")[1]) for code in start), default=0)
    created: list[TestCase] = []
    for designed in result.tests:
        counter += 1
        blocked = any(issue.severity == IssueSeverity.BLOCK for issue in designed.issues)
        test = TestCase(
            spec_id=spec.id, tc_code=f"TC-{counter:03d}", origin=designed.origin,
            technique=designed.technique, inputs=dict(designed.inputs), fixture_hash=designed.fixture_hash,
            assertion=designed.assertion, expected=dict(designed.expected),
            ai_claimed_expected=dict(designed.ai_claimed_expected) if designed.ai_claimed_expected else None,
            rationale=designed.rationale, risk_score=designed.risk_score,
            status=TestStatus.BLOCKED if blocked else TestStatus.DRAFT,
        )
        db.add(test)
        created.append(test)
    db.flush()

    # Link order carries meaning (the first rule is the test's primary rule), so stamp links with
    # strictly increasing times instead of relying on identical default timestamps.
    clock = utc_now()
    ticks = 0

    def stamp() -> Any:
        nonlocal ticks
        ticks += 1
        return clock + timedelta(microseconds=ticks)

    for designed, test in zip(result.tests, created):
        for issue in designed.issues:
            db.add(ValidationIssueRecord(
                spec_id=spec.id, entity_type=EntityType.TEST_CASE, entity_id=test.id, code=issue.code,
                severity=issue.severity, message=issue.message, field_path=issue.field_path,
                detail=issue.detail, active=True))
        for key in designed.rule_keys:
            db.add(TraceLink(spec_id=spec.id, from_type=EntityType.TEST_CASE, from_id=test.id,
                             to_type=EntityType.RULE, to_id=rules[key].id, link_type=TraceLinkType.VERIFIES,
                             created_at=stamp()))
        for code in designed.criterion_codes:
            db.add(TraceLink(spec_id=spec.id, from_type=EntityType.TEST_CASE, from_id=test.id,
                             to_type=EntityType.CRITERION, to_id=criterion_rows[code].id,
                             link_type=TraceLinkType.COVERS, created_at=stamp()))
    for issue in result.plan_issues:
        db.add(ValidationIssueRecord(
            spec_id=spec.id, entity_type=EntityType.SPEC, entity_id=spec.id, code=issue.code,
            severity=issue.severity, message=issue.message, field_path=issue.field_path,
            detail=issue.detail, active=True))
    db.flush()
    return created


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


def build_test_responses(db: Session, tests: Sequence[TestCase]) -> list[TestCaseResponse]:
    """Build API responses with trace-derived rule, criterion and policy information."""
    if not tests:
        return []
    ids = [test.id for test in tests]
    links = db.scalars(
        select(TraceLink).where(TraceLink.from_type == EntityType.TEST_CASE, TraceLink.from_id.in_(ids))
        .order_by(TraceLink.created_at, TraceLink.id)
    ).all()
    rule_ids = {link.to_id for link in links if link.to_type == EntityType.RULE}
    criterion_ids = {link.to_id for link in links if link.to_type == EntityType.CRITERION}
    rules = {r.id: r for r in db.scalars(select(SpecRule).where(SpecRule.id.in_(rule_ids)))} if rule_ids else {}
    criteria = ({c.id: c for c in db.scalars(select(Criterion).where(Criterion.id.in_(criterion_ids)))}
                if criterion_ids else {})
    issues: dict[uuid.UUID, list[ValidationIssueRecord]] = defaultdict(list)
    for record in db.scalars(
        select(ValidationIssueRecord).where(
            ValidationIssueRecord.entity_type == EntityType.TEST_CASE,
            ValidationIssueRecord.entity_id.in_(ids), ValidationIssueRecord.active.is_(True))
        .order_by(ValidationIssueRecord.created_at, ValidationIssueRecord.id)
    ):
        issues[record.entity_id].append(record)

    rule_keys: dict[uuid.UUID, list[str]] = defaultdict(list)
    policy_refs: dict[uuid.UUID, list[str]] = defaultdict(list)
    codes: dict[uuid.UUID, list[str]] = defaultdict(list)
    for link in links:
        if link.link_type == TraceLinkType.VERIFIES and link.to_id in rules:
            rule = rules[link.to_id]
            if rule.rule_key not in rule_keys[link.from_id]:
                rule_keys[link.from_id].append(rule.rule_key)
            if rule.policy_ref and rule.policy_ref not in policy_refs[link.from_id]:
                policy_refs[link.from_id].append(rule.policy_ref)
        elif link.link_type == TraceLinkType.COVERS and link.to_id in criteria:
            code = criteria[link.to_id].crit_code
            if code not in codes[link.from_id]:
                codes[link.from_id].append(code)

    return [
        TestCaseResponse.model_validate({
            "id": test.id, "spec_id": test.spec_id, "tc_code": test.tc_code, "origin": test.origin,
            "technique": test.technique, "inputs": dict(test.inputs), "assertion": test.assertion,
            "expected": ExpectedResult.model_validate(test.expected),
            "ai_claimed_expected": (ExpectedResult.model_validate(test.ai_claimed_expected)
                                    if test.ai_claimed_expected else None),
            "rationale": test.rationale, "risk_score": test.risk_score, "status": test.status,
            "rule_keys": rule_keys[test.id], "criterion_codes": codes[test.id],
            "policy_refs": policy_refs[test.id],
            "issues": [ValidationIssue(
                code=r.code, severity=r.severity, message=r.message, field_path=r.field_path,
                detail=dict(r.detail) if r.detail else None) for r in issues[test.id]],
            "supersedes_id": test.supersedes_id, "created_at": test.created_at,
        })
        for test in tests
    ]


# ---------------------------------------------------------------------------
# Design
# ---------------------------------------------------------------------------


def _log_edge_call(db: Session, ai: RequirementAI, *, input_hash: str, result: Any = None,
                   error_code: str | None = None) -> None:
    """Persist the AI edge-case call immediately so it survives later failures."""
    db.add(LlmCall(
        stage=LlmStage.EDGE_CASES, provider=ai.provider, model=ai.model,
        prompt_version=getattr(result, "prompt_version", "n/a"), input_hash=input_hash,
        output_hash=(sha256_hex([s.model_dump(mode="json") for s in result.data]) if result is not None else None),
        valid_first_try=bool(result.valid_first_try) if result is not None else False,
        retries=getattr(result, "retries", 0) if result is not None else 0,
        latency_ms=getattr(result, "latency_ms", None), tokens_in=getattr(result, "tokens_in", None),
        tokens_out=getattr(result, "tokens_out", None), fallback=False, error_code=error_code))
    db.commit()


def design_tests(
    db: Session, spec_id: uuid.UUID, payload: DesignTestsRequest, *, engine: QualityEngine,
    ai: RequirementAI | None, trace_id: str | None,
) -> DesignTestsResponse:
    """Design, validate and store tests for an APPROVED specification."""
    require_role(payload.actor_role, SPEC_EDITOR_ROLES, "design tests")
    spec = load_spec(db, spec_id)
    if spec.status != SpecStatus.APPROVED:
        raise StateTransitionError(
            "Tests can only be designed for an APPROVED specification.",
            details={"spec_id": str(spec.id), "spec_status": SpecStatus(spec.status).value})
    existing = list(db.scalars(select(TestCase).where(TestCase.spec_id == spec.id)))
    present = {(TestOrigin(t.origin), t.fixture_hash) for t in existing}
    has_ai = any(t.origin == TestOrigin.AI for t in existing)

    engine_spec = engine_spec_for(db, spec, engine)
    suggestions: list[Any] = []
    ai_state, ai_message = "disabled", None
    if payload.include_ai_edge_cases and has_ai:
        ai_state = "already_present"  # AI edge cases are added once; they are never regenerated
    elif payload.include_ai_edge_cases:
        if ai is None:
            ai_state, ai_message = "unavailable", AI_UNAVAILABLE_MESSAGE
        else:
            input_hash = sha256_hex(spec_snapshot(spec)) or ""
            try:
                ai_result = ai.suggest_edge_cases(spec=build_spec_response(db, spec))
                suggestions = list(ai_result.data)
                _log_edge_call(db, ai, input_hash=input_hash, result=ai_result)
                ai_state = "generated"
            except Exception as exc:  # any provider failure: keep the engine tests usable
                code = getattr(getattr(exc, "code", None), "value", ErrorCode.AI_PROVIDER_ERROR.value)
                _log_edge_call(db, ai, input_hash=input_hash, error_code=code)
                ai_state, ai_message = "unavailable", AI_UNAVAILABLE_MESSAGE

    criteria = call_engine(lambda: engine.derive_criteria(engine_spec))
    designed = call_engine(lambda: engine.design_tests(engine_spec, suggestions))
    fresh = tuple(t for t in designed.tests if (t.origin, t.fixture_hash) not in present)
    result = DesignResult(fresh, designed.plan_issues if not existing else ())
    created = persist_design(db, spec, result, criteria)
    already_present = len(designed.tests) - len(fresh)
    record_audit_event(
        db, actor=payload.actor, actor_role=payload.actor_role, action=AuditAction.TESTS_DESIGNED,
        entity_type=EntityType.SPEC, entity_id=spec.id, after=spec_snapshot(spec), trace_id=trace_id,
        detail={"added": len(created), "already_present": already_present,
                "blocked_added": sum(1 for t in created if t.status == TestStatus.BLOCKED),
                "ai_edge_cases": ai_state, "criteria": len(criteria)})
    db.commit()

    responses = build_test_responses(
        db, list(db.scalars(select(TestCase).where(TestCase.spec_id == spec.id).order_by(TestCase.tc_code))))
    counts: dict[TestTechnique, int] = defaultdict(int)
    for test in responses:
        counts[test.technique] += 1
    criterion_rows = db.scalars(select(Criterion).where(Criterion.spec_id == spec.id).order_by(Criterion.crit_code)).all()
    return DesignTestsResponse.model_validate({
        "spec_id": spec.id,
        "criteria": [CriterionResponse(id=c.id, spec_id=c.spec_id, crit_code=c.crit_code, rule_key=c.rule_key,
                                       given=c.given_text, when=c.when_text, then=c.then_text)
                     for c in criterion_rows],
        "tests": responses, "counts_by_technique": dict(counts),
        "blocked_count": sum(1 for t in responses if t.status == TestStatus.BLOCKED),
        "ai_edge_cases": ai_state, "ai_message": ai_message,
        "added": len(created), "already_present": already_present,
    })


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_tests(
    db: Session, spec_id: uuid.UUID, *, status: TestStatus | None, technique: TestTechnique | None,
    origin: TestOrigin | None,
) -> list[TestCaseResponse]:
    load_spec(db, spec_id)
    query = select(TestCase).where(TestCase.spec_id == spec_id).order_by(TestCase.tc_code)
    if status is not None:
        query = query.where(TestCase.status == status)
    if technique is not None:
        query = query.where(TestCase.technique == technique)
    if origin is not None:
        query = query.where(TestCase.origin == origin)
    return build_test_responses(db, list(db.scalars(query)))


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


def _blocking_codes(db: Session, test: TestCase) -> list[str]:
    return sorted({
        ValidationCode(r.code).value for r in db.scalars(
            select(ValidationIssueRecord).where(
                ValidationIssueRecord.entity_type == EntityType.TEST_CASE,
                ValidationIssueRecord.entity_id == test.id, ValidationIssueRecord.active.is_(True),
                ValidationIssueRecord.severity == IssueSeverity.BLOCK))
    })


def review_tests(db: Session, payload: TestReviewRequest, *, trace_id: str | None) -> TestReviewResponse:
    """Approve or reject tests; refusals are explained and never abort the whole request."""
    require_role(payload.actor_role, SPEC_EDITOR_ROLES, "review tests")
    rows = {t.id: t for t in db.scalars(select(TestCase).where(TestCase.id.in_(payload.test_ids)))}
    unknown = [str(i) for i in payload.test_ids if i not in rows]
    if unknown:
        raise NotFoundError("Unknown test IDs.", details={"unknown_test_ids": unknown})

    approving = payload.decision == ReviewDecision.APPROVE
    target = TestStatus.APPROVED if approving else TestStatus.REJECTED
    bulk = len(payload.test_ids) > 1
    reviewed: list[TestReviewItem] = []
    refused: list[TestReviewRefusal] = []

    def refuse(test: TestCase, code: ErrorCode, message: str) -> None:
        refused.append(TestReviewRefusal(test_id=test.id, code=code, message=message))

    for test_id in payload.test_ids:
        test = rows[test_id]
        status = TestStatus(test.status)
        if status == TestStatus.BLOCKED:
            codes = ", ".join(_blocking_codes(db, test)) or "validation"
            refuse(test, ErrorCode.TEST_NOT_APPROVABLE, f"{test.tc_code} is BLOCKED ({codes}).")
        elif status not in (TestStatus.DRAFT, TestStatus.STALE):
            refuse(test, ErrorCode.STATE_TRANSITION_NOT_ALLOWED,
                   f"{test.tc_code} is {status.value}; only DRAFT or STALE tests can be reviewed.")
        elif test.spec.status != SpecStatus.APPROVED:
            refuse(test, ErrorCode.STATE_TRANSITION_NOT_ALLOWED,
                   f"{test.tc_code} belongs to a specification that is not APPROVED.")
        elif approving and bulk and test.origin == TestOrigin.AI:
            refuse(test, ErrorCode.TEST_NOT_APPROVABLE,
                   f"{test.tc_code} is AI-generated and must be approved individually.")
        else:
            assert_test_transition(status, target)
            before = test_snapshot(test)  # before the claim: the ORM-aware UPDATE syncs the object
            # Claim the transition atomically: of two concurrent reviews only one UPDATE matches the status.
            claimed = db.execute(
                update(TestCase).where(TestCase.id == test.id, TestCase.status == status).values(status=target)
            ).rowcount
            if claimed != 1:
                refuse(test, ErrorCode.STATE_TRANSITION_NOT_ALLOWED,
                       f"{test.tc_code} was changed by another request and was not reviewed.")
                continue
            test.status = target
            db.add(Review(entity_type=EntityType.TEST_CASE, entity_id=test.id,
                          decision=payload.decision, reviewer=payload.actor,
                          reviewer_role=payload.actor_role, reason=payload.reason))
            record_audit_event(
                db, actor=payload.actor, actor_role=payload.actor_role,
                action=AuditAction.TEST_APPROVED if approving else AuditAction.TEST_REJECTED,
                entity_type=EntityType.TEST_CASE, entity_id=test.id, before=before,
                after=test_snapshot(test), trace_id=trace_id,
                detail={"tc_code": test.tc_code, "reason": payload.reason, "origin": TestOrigin(test.origin).value})
            reviewed.append(TestReviewItem(test_id=test.id, tc_code=test.tc_code,
                                           previous_status=status, new_status=target))
    db.commit()
    return TestReviewResponse(decision=payload.decision, reviewed=reviewed, refused=refused)
