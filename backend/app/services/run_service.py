"""Runs against the mock Time-to-Pay API, results, and defect clustering.

* Only APPROVED tests of an APPROVED specification run, through Member 2's allowlisted runner.
* The target comes from ``MOCK_API_BASE_URL`` and must be a loopback address.
* An unreachable, blocked or malformed mock response is an ERROR result. It can never pass.

Defect lifecycle (documented decision): failures are clustered per run by Member 2's clustering
(rule, overnight flag, assertion). A new cluster opens a defect (OPEN). When all tests of an OPEN
defect run and pass, it becomes FIXED; when they pass again in a later run, VERIFIED. A cluster
that fails again reopens the defect.
"""

from __future__ import annotations

import copy
import uuid
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.config import LOOPBACK_HOSTS, Settings
from app.core.contracts import (
    AuditAction,
    DefectResponse,
    DefectStatus,
    EntityType,
    ErrorCode,
    ExpectedResult,
    IssueSeverity,
    ResultResponse,
    ResultStatus,
    ReviewDecision,
    RunCreateRequest,
    RunResponse,
    RunStatus,
    RunTotals,
    SpecStatus,
    TestStatus,
    ValidationCode,
)
from app.core.errors import ConflictError, IntegrationUnavailableError, NotFoundError, StateTransitionError
from app.core.state_machine import SPEC_EDITOR_ROLES, require_role
from app.database.base import utc_now
from app.engine.oracle import DomainError
from app.engine.protocol import FailureRecord, QualityEngine
from app.models import (
    Defect,
    Result,
    Review,
    Run,
    SutVersion,
    TestCase,
    TraceLink,
    TraceLinkType,
    ValidationIssueRecord,
)
from app.runner.executor import ExecutionBlocked, execute_cases
from app.services.engine_bridge import call_engine, engine_spec_for, load_spec

ENDPOINT_PATH = "/v1/pay/calculate"
SUT_NAME = "mock-time-to-pay"
MAX_EVIDENCE = 200
_ASSERT_FIELD = {"PAID_EQUALS": "paid_minutes", "OT_EQUALS": "overtime_minutes"}


def allowlisted_target(settings: Settings) -> tuple[str, str]:
    """Return (base URL, target URL), refusing anything that is not a loopback address."""
    parsed = urlparse(settings.mock_api_base_url)
    if parsed.hostname not in LOOPBACK_HOSTS or parsed.username or parsed.password:
        raise IntegrationUnavailableError(
            "The mock API must be on a loopback address (MOCK_API_BASE_URL).",
            details={"mock_api_base_url_host": parsed.hostname})
    return settings.mock_api_base_url, f"{settings.mock_api_base_url}{ENDPOINT_PATH}"


def discover_version(base_url: str, client: httpx.Client) -> str | None:
    """Ask the mock which implementation it is serving; ``None`` if it cannot be reached."""
    try:
        response = client.get(f"{base_url}/version")
        version = response.json().get("version") if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError, AttributeError):
        return None
    return version if isinstance(version, str) and 0 < len(version) <= 32 else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _internal_expected(oracle: Any, inputs: dict[str, Any]) -> dict[str, Any]:
    try:
        result = oracle(**inputs)
    except (DomainError, TypeError):
        return {"status_code": 422}
    return {"paid_minutes": result.paid_minutes, "overtime_minutes": result.overtime_minutes}


def _stored_matches(test: TestCase, internal: dict[str, Any]) -> bool:
    """The approved expected value must still equal the oracle's result."""
    expected = test.expected
    if test.assertion.value == "REJECTS":
        return expected.get("rejects") is True and internal == {"status_code": 422}
    field = _ASSERT_FIELD[test.assertion.value]
    return internal.get(field) is not None and expected.get(field) == internal[field]


def _failed_assertion(test: TestCase, outcome: dict[str, Any]) -> str | None:
    status, actual = outcome["status"], outcome["actual"]
    if status == "ERROR":
        return str(outcome.get("error") or "The test could not be executed.")[:300]
    if status == "PASS":
        return None
    if test.assertion.value == "REJECTS":
        return f"expected rejection (422), observed status {(actual or {}).get('status_code')}"[:300]
    field = _ASSERT_FIELD[test.assertion.value]
    observed = (actual or {}).get(field)
    return f"{field} expected {outcome['expected'].get(field)}, observed {observed}"[:300]


def _links(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    rules: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for link in db.scalars(
        select(TraceLink).where(
            TraceLink.from_type == EntityType.TEST_CASE, TraceLink.from_id.in_(ids),
            TraceLink.link_type == TraceLinkType.VERIFIES).order_by(TraceLink.created_at, TraceLink.id)
    ):
        rules[link.from_id].append(link.to_id)
    return rules


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def create_run(
    db: Session, payload: RunCreateRequest, *, engine: QualityEngine, settings: Settings,
    trace_id: str | None, client: httpx.Client | None = None,
) -> RunResponse:
    """Execute approved tests and store results, defects and audit events in one transaction."""
    require_role(payload.actor_role, SPEC_EDITOR_ROLES, "run tests")
    spec = load_spec(db, payload.spec_id)
    if spec.status != SpecStatus.APPROVED:
        raise StateTransitionError(
            "Tests can only be run for an APPROVED specification.",
            details={"spec_id": str(spec.id), "spec_status": SpecStatus(spec.status).value})

    query = select(TestCase).where(TestCase.spec_id == spec.id).order_by(TestCase.tc_code)
    if payload.test_ids is not None:
        query = query.where(TestCase.id.in_(payload.test_ids))
    tests = list(db.scalars(query))
    if payload.test_ids is not None:
        found = {t.id for t in tests}
        missing = [str(i) for i in payload.test_ids if i not in found]
        if missing:
            raise NotFoundError("Unknown test IDs for this specification.", details={"unknown_test_ids": missing})
        not_approved = [{"test_id": str(t.id), "status": TestStatus(t.status).value}
                        for t in tests if t.status != TestStatus.APPROVED]
        if not_approved:
            raise ConflictError("Only APPROVED tests can run.", details={"not_approved": not_approved})
    else:
        tests = [t for t in tests if t.status == TestStatus.APPROVED]
    if not tests:
        raise ConflictError("The specification has no APPROVED tests to run.", details={"spec_id": str(spec.id)})

    base_url, target = allowlisted_target(settings)
    engine_spec = engine_spec_for(db, spec, engine)
    oracle = call_engine(lambda: engine.oracle(engine_spec))
    requirement_code = spec.requirement_version.requirement.code
    policy_codes = [p.policy_code for p in engine_spec.policies]
    rule_ids = _links(db, [t.id for t in tests])
    rule_keys_by_id = {r.id: r.rule_key for r in spec.rules}

    own_client = client is None
    http = client or httpx.Client(timeout=httpx.Timeout(3.0, connect=1.0), follow_redirects=False, trust_env=False)
    try:
        version = discover_version(base_url, http)
        run = Run(spec_id=spec.id, sut_version=version or "unknown", trigger=payload.trigger,
                  status=RunStatus.RUNNING, actor=payload.actor, started_at=utc_now(), total=len(tests))
        sut = db.scalar(select(SutVersion).where(SutVersion.name == SUT_NAME, SutVersion.version == run.sut_version))
        run.sut_version_id = sut.id if sut else None
        db.add(run)
        db.flush()

        outcomes: list[tuple[TestCase, dict[str, Any], str]] = []
        for test in tests:
            primary = rule_keys_by_id.get(rule_ids[test.id][0]) if rule_ids[test.id] else "UNKNOWN"
            outcome = _execute_one(db, test, requirement_code=requirement_code, policy_codes=policy_codes,
                                   oracle=oracle, version=version, target=target, http=http)
            outcomes.append((test, outcome, primary))
    finally:
        if own_client:
            http.close()

    results: list[Result] = []
    for test, outcome, _primary in outcomes:
        status = ResultStatus(outcome["status"])
        results.append(Result(
            run_id=run.id, test_case_id=test.id, status=status, expected=dict(test.expected),
            observed=outcome["actual"], failed_assertion=_failed_assertion(test, outcome),
            latency_ms=int(outcome.get("duration_ms") or 0)))
    db.add_all(results)
    db.flush()

    run.passed = sum(1 for r in results if r.status == ResultStatus.PASS)
    run.failed = sum(1 for r in results if r.status == ResultStatus.FAIL)
    run.errors = sum(1 for r in results if r.status == ResultStatus.ERROR)
    run.status = RunStatus.FAILED if run.errors == run.total else RunStatus.COMPLETED
    run.finished_at = utc_now()

    by_test = {r.test_case_id: r for r in results}
    _update_defects(db, spec.id, run, outcomes, by_test, engine, payload, trace_id)
    record_audit_event(
        db, actor=payload.actor, actor_role=payload.actor_role, action=AuditAction.RUN_EXECUTED,
        entity_type=EntityType.RUN, entity_id=run.id, after={"id": str(run.id), "status": run.status.value,
        "total": run.total, "passed": run.passed, "failed": run.failed, "errors": run.errors},
        trace_id=trace_id, detail={"spec_id": str(spec.id), "sut_version": run.sut_version,
                                   "trigger": payload.trigger.value, "total": run.total, "passed": run.passed,
                                   "failed": run.failed, "errors": run.errors})
    db.commit()
    return get_run(db, run.id)


def _execute_one(
    db: Session, test: TestCase, *, requirement_code: str, policy_codes: list[str], oracle: Any,
    version: str | None, target: str, http: httpx.Client,
) -> dict[str, Any]:
    """Run one approved test through the allowlisted runner; failures are ERROR, never PASS."""
    def error(message: str, actual: Any = None) -> dict[str, Any]:
        return {"status": "ERROR", "actual": actual, "error": message, "expected": dict(test.expected),
                "duration_ms": 0}

    if version is None:
        return error("The mock API is unreachable or did not report its version.")
    internal = _internal_expected(oracle, dict(test.inputs))
    if not _stored_matches(test, internal):
        return error("The approved expected value no longer matches the deterministic oracle.")
    approval = db.scalars(
        select(Review).where(Review.entity_type == EntityType.TEST_CASE, Review.entity_id == test.id,
                             Review.decision == ReviewDecision.APPROVE).order_by(Review.created_at.desc())
    ).first()
    if approval is None:
        return error("No human approval record exists for this test.")
    issue_records = db.scalars(
        select(ValidationIssueRecord).where(
            ValidationIssueRecord.entity_type == EntityType.TEST_CASE, ValidationIssueRecord.entity_id == test.id,
            ValidationIssueRecord.active.is_(True)).order_by(ValidationIssueRecord.created_at, ValidationIssueRecord.id)
    ).all()
    issues = [{"code": ValidationCode(r.code).value[:3],
               "severity": "BLOCK" if r.severity == IssueSeverity.BLOCK else "WARNING",
               "test_id": str(test.id)} for r in issue_records]
    case = {
        "id": str(test.id), "version": 1, "requirement_id": requirement_code, "criterion_id": None,
        "policy_ids": policy_codes, "rule_key": "RQ-014:TIME_TO_PAY", "technique": test.technique.value,
        "partition": test.technique.value, "inputs": dict(test.inputs), "assertion_type": test.assertion.value,
        "expected": internal, "validation_state": "VALID", "approval_state": "APPROVED",
    }
    record = {"case": copy.deepcopy(case), "issues": issues,
              "approval": {"test_id": str(test.id), "case_version": 1, "decision": "APPROVED",
                           "reviewer_id": approval.reviewer, "warnings_acknowledged": True}}
    try:
        outcomes = execute_cases(
            [case], selected_version=version, issues=issues, load_reviewed_case=lambda _id: copy.deepcopy(record),
            target=target, allowed_target=target, client=http, oracle=oracle)
    except ExecutionBlocked as exc:
        return error(f"Execution blocked: {exc}")
    outcome = outcomes[0]
    outcome["expected"] = dict(test.expected)
    outcome["actual"] = outcome.get("actual")
    return outcome


# ---------------------------------------------------------------------------
# Defects
# ---------------------------------------------------------------------------


def _defect_snapshot(defect: Defect) -> dict[str, Any]:
    return {"id": str(defect.id), "cluster_key": defect.cluster_key, "status": DefectStatus(defect.status).value}


def _get_or_create_defect(
    db: Session, spec_id: uuid.UUID, cluster: Any, run: Run, existing: dict[str, Defect],
) -> tuple[Defect, bool]:
    """Return the defect for ``cluster``; a concurrent run creating it first is handled, not a 500."""
    defect = existing.get(cluster.cluster_key)
    if defect is not None:
        return defect, False
    candidate = Defect(spec_id=spec_id, cluster_key=cluster.cluster_key, title=cluster.title[:200],
                       rule_key=cluster.rule_key, partition=dict(cluster.partition), status=DefectStatus.OPEN,
                       first_run_id=run.id, last_run_id=run.id,
                       evidence_result_ids=list(cluster.result_ids)[:MAX_EVIDENCE])
    try:
        with db.begin_nested():
            db.add(candidate)
            db.flush()
    except IntegrityError:
        if candidate in db:
            db.expunge(candidate)
        winner = db.scalar(select(Defect).where(Defect.spec_id == spec_id, Defect.cluster_key == cluster.cluster_key))
        if winner is None:
            raise
        existing[cluster.cluster_key] = winner
        return winner, False
    existing[cluster.cluster_key] = candidate
    return candidate, True


def _update_defects(
    db: Session, spec_id: uuid.UUID, run: Run, outcomes: list[tuple[TestCase, dict[str, Any], str]],
    by_test: dict[uuid.UUID, Result], engine: QualityEngine, payload: RunCreateRequest, trace_id: str | None,
) -> None:
    failures = [
        FailureRecord(result_id=str(by_test[test.id].id), test_id=str(test.id), rule_key=primary,
                      overnight=bool(test.inputs.get("overnight")), assertion=test.assertion.value)
        for test, outcome, primary in outcomes if outcome["status"] == "FAIL"
    ]
    clusters = call_engine(lambda: engine.cluster_failures(failures))
    existing = {d.cluster_key: d for d in db.scalars(select(Defect).where(Defect.spec_id == spec_id))}
    failing_keys = {c.cluster_key for c in clusters}

    def audit(defect: Defect, before: dict[str, Any] | None, change: str) -> None:
        record_audit_event(
            db, actor=payload.actor, actor_role=payload.actor_role, action=AuditAction.DEFECT_UPDATED,
            entity_type=EntityType.DEFECT, entity_id=defect.id, before=before, after=_defect_snapshot(defect),
            trace_id=trace_id, detail={"change": change, "run_id": str(run.id), "cluster_key": defect.cluster_key})

    for cluster in clusters:
        defect, created = _get_or_create_defect(db, spec_id, cluster, run, existing)
        if created:
            audit(defect, None, "opened")
        else:
            before = _defect_snapshot(defect)
            merged = list(dict.fromkeys([*defect.evidence_result_ids, *cluster.result_ids]))[-MAX_EVIDENCE:]
            defect.evidence_result_ids = merged
            defect.last_run_id = run.id
            if defect.status != DefectStatus.OPEN:
                defect.status = DefectStatus.OPEN
                audit(defect, before, "reopened")

    ran = {test.id: outcome["status"] for test, outcome, _p in outcomes}
    for key, defect in existing.items():
        if key in failing_keys or defect.status == DefectStatus.VERIFIED:
            continue
        evidence = [uuid.UUID(i) for i in defect.evidence_result_ids]
        test_ids = {r.test_case_id for r in db.scalars(select(Result).where(Result.id.in_(evidence)))} if evidence else set()
        if test_ids and all(ran.get(t) == "PASS" for t in test_ids):
            before = _defect_snapshot(defect)
            defect.status = DefectStatus.FIXED if defect.status == DefectStatus.OPEN else DefectStatus.VERIFIED
            defect.last_run_id = run.id
            audit(defect, before, defect.status.value.lower())


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def get_run(db: Session, run_id: uuid.UUID) -> RunResponse:
    run = db.get(Run, run_id)
    if run is None:
        raise NotFoundError(f"Run {run_id} was not found.", details={"run_id": str(run_id)})
    rows = db.execute(
        select(Result, TestCase.tc_code).join(TestCase, Result.test_case_id == TestCase.id)
        .where(Result.run_id == run.id).order_by(TestCase.tc_code)).all()
    return RunResponse.model_validate({
        "id": run.id, "spec_id": run.spec_id, "sut_version": run.sut_version, "trigger": run.trigger,
        "status": run.status, "started_at": run.started_at, "finished_at": run.finished_at,
        "totals": RunTotals(total=run.total, passed=run.passed, failed=run.failed, errors=run.errors),
        "results": [ResultResponse(
            id=r.id, run_id=r.run_id, test_case_id=r.test_case_id, tc_code=code, status=r.status,
            expected=ExpectedResult.model_validate(r.expected), observed=r.observed,
            failed_assertion=r.failed_assertion, latency_ms=r.latency_ms) for r, code in rows],
    })


def list_defects(db: Session, *, status: DefectStatus | None, spec_id: uuid.UUID | None) -> list[DefectResponse]:
    query = select(Defect).order_by(Defect.created_at, Defect.cluster_key)
    if status is not None:
        query = query.where(Defect.status == status)
    if spec_id is not None:
        query = query.where(Defect.spec_id == spec_id)
    return [
        DefectResponse.model_validate({
            "id": d.id, "cluster_key": d.cluster_key, "title": d.title, "rule_key": d.rule_key,
            "partition": dict(d.partition), "status": d.status, "first_run_id": d.first_run_id,
            "evidence_result_ids": [uuid.UUID(i) for i in d.evidence_result_ids],
            "hypothesis": d.hypothesis, "created_at": d.created_at})
        for d in db.scalars(query)
    ]
