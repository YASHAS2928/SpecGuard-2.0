"""Analysis, ambiguity resolution and specification approval tests."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Sequence
from typing import Any

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select

import pytest

from app.ai.schemas import AIResult, EdgeCaseSuggestion
from app.core.config import FAKE_MODEL_NAME, Settings, get_settings
from app.core.contracts import (
    RQ014_EXTRACTION_EXAMPLE,
    AIProvider,
    AuditAction,
    IssueSeverity,
    PolicyResponse,
    RequirementExtraction,
    ReviewDecision,
    ValidationCode,
    ValidationIssue,
)
from app.core.dependencies import get_ai
from app.core.errors import AIOutputInvalidError, AIProviderError
from app.database.session import SessionLocal
from app.models import AuditEvent, LlmCall, RequirementVersion, Review
from app.services.integration_service import get_spec_checker

RQ014_TEXT = (
    "For an overnight shift, calculate overtime correctly after the employee has worked "
    "the configured number of paid hours, excluding the unpaid meal break."
)
V1_POLICIES = ["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"]
V2_POLICIES = ["POL-OT-01@v2", "POL-MEAL-02@v1", "POL-DATE-03@v1"]
BA = {"actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"}


# --- Test doubles ------------------------------------------------------------------


def _normalise(text: str) -> str:
    return " ".join(text.split()).lower()


def reference_checker(
    extraction: RequirementExtraction, requirement_text: str, policies: Sequence[PolicyResponse]
) -> list[ValidationIssue]:
    """Test-only stand-in for Member 2's grounding check (V02)."""
    haystacks = [_normalise(requirement_text), *(_normalise(p.rule_text) for p in policies)]
    issues: list[ValidationIssue] = []
    for rule in extraction.rules:
        if not any(_normalise(rule.source_span) in haystack for haystack in haystacks):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.V02_UNGROUNDED_SPAN,
                    severity=IssueSeverity.BLOCK,
                    message=f"Source span of {rule.rule_key} was not found in the sources.",
                    field_path=f"rules.{rule.rule_key}.source_span",
                    detail={"rule_key": rule.rule_key},
                )
            )
    return issues


class StubAI:
    provider = AIProvider.FAKE
    model = "stub-model"

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def extract_requirement(
        self, *, requirement_text: str, policies: Sequence[PolicyResponse]
    ) -> AIResult[RequirementExtraction]:
        return AIResult(
            data=RequirementExtraction.model_validate(self._data),
            provider=self.provider,
            model=self.model,
            prompt_version="stub-1.0",
            valid_first_try=True,
        )

    def suggest_edge_cases(self, *, spec: Any) -> AIResult[list[EdgeCaseSuggestion]]:
        raise NotImplementedError


class FailingAI:
    provider = AIProvider.GROQ
    model = "failing-model"

    def __init__(self, error: Exception) -> None:
        self._error = error

    def extract_requirement(self, *, requirement_text: str, policies: Sequence[PolicyResponse]) -> Any:
        raise self._error

    def suggest_edge_cases(self, *, spec: Any) -> Any:
        raise NotImplementedError


# --- Helpers -------------------------------------------------------------------------


@pytest.fixture()
def api(client: TestClient) -> TestClient:
    client.app.dependency_overrides[get_spec_checker] = lambda: reference_checker  # type: ignore[attr-defined]
    return client


def use_ai(client: TestClient, provider: Any) -> None:
    client.app.dependency_overrides[get_ai] = lambda: provider  # type: ignore[attr-defined]


def create_requirement(client: TestClient, policies: list[str] = V1_POLICIES) -> dict[str, Any]:
    response = client.post(
        "/requirements",
        json={
            "code": f"RQ-{uuid.uuid4().int % 900000 + 100000}",
            "title": "Overnight overtime with unpaid meal break",
            "text": RQ014_TEXT,
            "policy_ids": policies,
            **BA,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def analyze(client: TestClient, version_id: str, **extra: Any) -> Response:
    return client.post(f"/requirement-versions/{version_id}/analyze", json={**BA, **extra})


def analyzed(client: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    requirement = create_requirement(client)
    response = analyze(client, requirement["versions"][0]["id"])
    assert response.status_code == 200, response.text
    return requirement, response.json()


def resolve(client: TestClient, ambiguity_id: str, **body: Any) -> Response:
    return client.post(f"/ambiguities/{ambiguity_id}/resolve", json={**BA, **body})


def approve(client: TestClient, spec_id: str, **body: Any) -> Response:
    return client.post(f"/specs/{spec_id}/approve", json={**BA, **body})


def resolved_and_approved(client: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    requirement, body = analyzed(client)
    spec = body["spec"]
    assert resolve(client, spec["ambiguities"][0]["id"], option_index=0).status_code == 200
    response = approve(client, spec["id"])
    assert response.status_code == 200, response.text
    return requirement, response.json()


# --- Analysis --------------------------------------------------------------------------


def test_analyze_creates_a_draft_spec_with_grounded_rules(api: TestClient) -> None:
    requirement, body = analyzed(api)
    spec = body["spec"]
    assert spec["status"] == "DRAFT" and spec["version"] == 1
    assert spec["requirement_version_id"] == requirement["versions"][0]["id"]
    assert spec["parent_spec_id"] is None

    rules = {rule["rule_key"]: rule for rule in spec["rules"]}
    assert set(rules) == {"OT_THRESHOLD", "MEAL_DEDUCTION", "SHIFT_SPAN", "END_BEFORE_START"}
    assert all(rule["grounded"] is True for rule in rules.values())
    assert rules["OT_THRESHOLD"]["params"]["threshold"] == 480
    assert rules["MEAL_DEDUCTION"]["unresolved_params"] == ["min_qualifying"]
    assert spec["open_ambiguities"] == 1
    assert spec["blocking_issue_count"] == 1
    assert [issue["code"] for issue in spec["issues"]] == ["V13_UNRESOLVED_PARAMETER"]

    analysis = body["analysis"]
    assert analysis["mode"] == "fake" and analysis["provider"] == "fake"
    assert analysis["model"] == FAKE_MODEL_NAME
    assert analysis["fallback_used"] is False
    assert uuid.UUID(analysis["llm_call_id"])
    assert "no language model" in analysis["message"]


def test_analyze_moves_requirement_to_analyzed(api: TestClient) -> None:
    requirement, _ = analyzed(api)
    assert api.get(f"/requirements/{requirement['id']}").json()["status"] == "ANALYZED"


def test_analyze_unknown_version_returns_404(api: TestClient) -> None:
    response = analyze(api, str(uuid.uuid4()))
    assert response.status_code == 404


def test_developer_cannot_analyze(api: TestClient) -> None:
    requirement = create_requirement(api)
    response = api.post(
        f"/requirement-versions/{requirement['versions'][0]['id']}/analyze",
        json={"actor": "dev.one", "actor_role": "DEVELOPER"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_ungrounded_source_span_is_flagged_and_blocks(api: TestClient) -> None:
    data = copy.deepcopy(RQ014_EXTRACTION_EXAMPLE)
    data["rules"][0]["source_span"] = "paid minutes above 999 in a single shift are overtime"
    use_ai(api, StubAI(data))
    _, body = analyzed(api)
    spec = body["spec"]
    rules = {rule["rule_key"]: rule for rule in spec["rules"]}
    assert rules["OT_THRESHOLD"]["grounded"] is False
    assert rules["SHIFT_SPAN"]["grounded"] is True
    codes = {issue["code"] for issue in spec["issues"]}
    assert codes == {"V02_UNGROUNDED_SPAN", "V13_UNRESOLVED_PARAMETER"}
    assert spec["blocking_issue_count"] == 2


def test_missing_engine_check_leaves_rules_ungrounded_and_blocks_approval(
    client: TestClient,
) -> None:
    client.app.dependency_overrides[get_spec_checker] = lambda: None  # type: ignore[attr-defined]
    _, body = analyzed(client)
    spec = body["spec"]
    assert all(rule["grounded"] is None for rule in spec["rules"])
    assert "Grounding check unavailable" in body["analysis"]["message"]

    assert resolve(client, spec["ambiguities"][0]["id"], option_index=0).status_code == 200
    response = approve(client, spec["id"])
    assert response.status_code == 409
    details = response.json()["error"]["details"]
    assert details["ungrounded_rules"] == [
        "END_BEFORE_START",
        "MEAL_DEDUCTION",
        "OT_THRESHOLD",
        "SHIFT_SPAN",
    ]
    assert details["open_ambiguities"] == []


# --- AI failures ---------------------------------------------------------------------------


def test_provider_error_is_surfaced_and_logged(api: TestClient) -> None:
    requirement = create_requirement(api)
    version_id = requirement["versions"][0]["id"]
    use_ai(api, FailingAI(AIProviderError("Rate limit reached.", details={"retries": 1})))

    response = analyze(api, version_id)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_PROVIDER_ERROR"
    assert api.get(f"/requirement-versions/{version_id}/specs").json() == []

    with SessionLocal() as session:
        calls = session.scalars(select(LlmCall).where(LlmCall.error_code == "AI_PROVIDER_ERROR")).all()
    assert any(call.retries == 1 and call.fallback is False for call in calls)


def test_unexpected_provider_exception_does_not_leak_its_message(api: TestClient) -> None:
    requirement = create_requirement(api)
    use_ai(api, FailingAI(RuntimeError("secret-token-123")))
    response = analyze(api, requirement["versions"][0]["id"])
    assert response.status_code == 502
    assert "secret-token-123" not in response.text


def test_invalid_output_error_is_surfaced(api: TestClient) -> None:
    requirement = create_requirement(api)
    use_ai(api, FailingAI(AIOutputInvalidError("Still invalid after retry.")))
    response = analyze(api, requirement["versions"][0]["id"])
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_OUTPUT_INVALID"


def test_unconfigured_provider_returns_503_without_fallback(api: TestClient) -> None:
    api.app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[attr-defined]
        _env_file=None, ai_provider="groq"
    )
    requirement = create_requirement(api)
    response = analyze(api, requirement["versions"][0]["id"])
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "AI_PROVIDER_NOT_CONFIGURED"
    assert any("GROQ_API_KEY" in issue for issue in error["details"]["issues"])


# --- Ambiguity resolution ------------------------------------------------------------------------


def test_resolving_the_ambiguity_applies_the_patch(api: TestClient) -> None:
    _, body = analyzed(api)
    spec = body["spec"]
    response = resolve(api, spec["ambiguities"][0]["id"], option_index=0)
    assert response.status_code == 200
    updated = response.json()

    ambiguity = updated["ambiguities"][0]
    assert ambiguity["status"] == "RESOLVED" and ambiguity["chosen_option_index"] == 0
    assert ambiguity["resolved_by"] == "asha.ba"
    rules = {rule["rule_key"]: rule for rule in updated["rules"]}
    assert rules["MEAL_DEDUCTION"]["params"]["min_qualifying"] == 30
    assert rules["MEAL_DEDUCTION"]["origin"] == "CLARIFIED"
    assert rules["MEAL_DEDUCTION"]["unresolved_params"] == []
    assert updated["open_ambiguities"] == 0
    assert updated["blocking_issue_count"] == 0 and updated["issues"] == []


def test_out_of_range_option_is_rejected_without_changes(api: TestClient) -> None:
    _, body = analyzed(api)
    spec = body["spec"]
    response = resolve(api, spec["ambiguities"][0]["id"], option_index=3)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    unchanged = api.get(f"/specs/{spec['id']}").json()
    assert unchanged["ambiguities"][0]["status"] == "OPEN"
    assert unchanged["open_ambiguities"] == 1


def test_invalid_patch_is_rejected_and_changes_nothing(api: TestClient) -> None:
    data = copy.deepcopy(RQ014_EXTRACTION_EXAMPLE)
    data["ambiguities"][0]["options"][0]["patch"][0]["path"] = "/rules/MEAL_DEDUCTION/params/threshold"
    use_ai(api, StubAI(data))
    _, body = analyzed(api)
    spec = body["spec"]

    response = resolve(api, spec["ambiguities"][0]["id"], option_index=0)
    assert response.status_code == 422
    unchanged = api.get(f"/specs/{spec['id']}").json()
    rules = {rule["rule_key"]: rule for rule in unchanged["rules"]}
    assert rules["MEAL_DEDUCTION"]["params"]["min_qualifying"] is None
    assert unchanged["ambiguities"][0]["status"] == "OPEN"


def test_resolving_twice_is_a_state_transition_error(api: TestClient) -> None:
    _, body = analyzed(api)
    ambiguity_id = body["spec"]["ambiguities"][0]["id"]
    assert resolve(api, ambiguity_id, option_index=0).status_code == 200
    response = resolve(api, ambiguity_id, option_index=1)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_TRANSITION_NOT_ALLOWED"


def test_deferred_ambiguity_blocks_approval_until_resolved(api: TestClient) -> None:
    _, body = analyzed(api)
    spec = body["spec"]
    ambiguity_id = spec["ambiguities"][0]["id"]

    deferred = resolve(api, ambiguity_id, defer=True, comment="Waiting for payroll owner.")
    assert deferred.status_code == 200
    assert deferred.json()["ambiguities"][0]["status"] == "DEFERRED"
    assert deferred.json()["open_ambiguities"] == 1

    blocked = approve(api, spec["id"])
    assert blocked.status_code == 409
    details = blocked.json()["error"]["details"]
    assert details["deferred_ambiguities"] == ["AMB-1"]
    assert details["open_ambiguities"] == []
    assert details["unresolved_params"] == ["MEAL_DEDUCTION.min_qualifying"]

    final = resolve(api, ambiguity_id, option_index=1)
    assert final.status_code == 200
    rules = {rule["rule_key"]: rule for rule in final.json()["rules"]}
    assert rules["MEAL_DEDUCTION"]["params"]["min_qualifying"] == 0


# --- Approval -------------------------------------------------------------------------------------


def test_approval_is_blocked_while_the_ambiguity_is_open(api: TestClient) -> None:
    _, body = analyzed(api)
    response = approve(api, body["spec"]["id"])
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "SPEC_NOT_APPROVABLE"
    assert error["details"]["open_ambiguities"] == ["AMB-1"]
    assert error["details"]["unresolved_params"] == ["MEAL_DEDUCTION.min_qualifying"]
    assert error["details"]["blocking_issues"] == ["V13_UNRESOLVED_PARAMETER"]
    assert error["details"]["ungrounded_rules"] == []


def test_approving_a_resolved_spec_succeeds(api: TestClient) -> None:
    requirement, approved = resolved_and_approved(api)
    assert approved["status"] == "APPROVED"
    assert approved["approved_by"] == "asha.ba" and approved["approved_at"]
    assert api.get(f"/requirements/{requirement['id']}").json()["status"] == "SPEC_APPROVED"


def test_approving_twice_is_a_state_transition_error(api: TestClient) -> None:
    _, approved = resolved_and_approved(api)
    response = approve(api, approved["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_TRANSITION_NOT_ALLOWED"


def test_developer_cannot_approve(api: TestClient) -> None:
    _, body = analyzed(api)
    response = api.post(
        f"/specs/{body['spec']['id']}/approve",
        json={"actor": "dev.one", "actor_role": "DEVELOPER"},
    )
    assert response.status_code == 403


def test_approve_unknown_spec_returns_404(api: TestClient) -> None:
    assert approve(api, str(uuid.uuid4())).status_code == 404


# --- Versions and re-analysis -----------------------------------------------------------------------


def test_reanalysis_supersedes_drafts_and_approved_needs_force(api: TestClient) -> None:
    requirement, first = analyzed(api)
    version_id = requirement["versions"][0]["id"]

    second = analyze(api, version_id).json()["spec"]
    assert second["version"] == 2
    assert api.get(f"/specs/{first['spec']['id']}").json()["status"] == "SUPERSEDED"

    assert resolve(api, second["ambiguities"][0]["id"], option_index=0).status_code == 200
    assert approve(api, second["id"]).status_code == 200

    blocked = analyze(api, version_id)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "CONFLICT"

    forced = analyze(api, version_id, force=True)
    assert forced.status_code == 200
    assert forced.json()["spec"]["version"] == 3
    assert api.get(f"/specs/{second['id']}").json()["status"] == "APPROVED"
    listed = api.get(f"/requirement-versions/{version_id}/specs").json()
    assert [spec["version"] for spec in listed] == [1, 2, 3]


def test_new_requirement_version_links_parent_and_supersedes_on_approval(api: TestClient) -> None:
    requirement, first_approved = resolved_and_approved(api)

    created = api.post(
        f"/requirements/{requirement['id']}/versions",
        json={
            "text": RQ014_TEXT,
            "policy_ids": V2_POLICIES,
            "change_note": "POL-OT-01 v2 lowers the threshold to 450 minutes.",
            **BA,
        },
    )
    assert created.status_code == 201
    assert api.get(f"/requirements/{requirement['id']}").json()["status"] == "CHANGED"

    second = analyze(api, created.json()["id"]).json()["spec"]
    assert second["parent_spec_id"] == first_approved["id"]
    rules = {rule["rule_key"]: rule for rule in second["rules"]}
    assert rules["OT_THRESHOLD"]["params"]["threshold"] == 450
    assert rules["OT_THRESHOLD"]["policy_ref"] == "POL-OT-01@v2"
    assert all(rule["grounded"] is True for rule in second["rules"])

    assert resolve(api, second["ambiguities"][0]["id"], option_index=0).status_code == 200
    assert approve(api, second["id"]).status_code == 200
    assert api.get(f"/specs/{first_approved['id']}").json()["status"] == "SUPERSEDED"
    assert api.get(f"/requirements/{requirement['id']}").json()["status"] == "SPEC_APPROVED"


# --- Reads and audit ------------------------------------------------------------------------------------


def test_get_spec_matches_the_analysis_response(api: TestClient) -> None:
    _, body = analyzed(api)
    fetched = api.get(f"/specs/{body['spec']['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body["spec"]
    assert api.get(f"/specs/{uuid.uuid4()}").status_code == 404
    assert api.get("/specs/not-a-uuid").status_code == 422


def test_workflow_writes_audit_events_and_a_review(api: TestClient) -> None:
    _, body = analyzed(api)
    spec = body["spec"]
    ambiguity_id = spec["ambiguities"][0]["id"]
    assert resolve(api, ambiguity_id, option_index=0).status_code == 200
    assert approve(api, spec["id"], comment="Rules confirmed with payroll.").status_code == 200

    with SessionLocal() as session:
        spec_events = session.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(spec["id"]))
        ).all()
        ambiguity_events = session.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(ambiguity_id))
        ).all()
        reviews = session.scalars(
            select(Review).where(Review.entity_id == uuid.UUID(spec["id"]))
        ).all()

    assert {event.action for event in spec_events} == {
        AuditAction.REQUIREMENT_ANALYZED,
        AuditAction.SPEC_APPROVED,
    }
    approved = next(e for e in spec_events if e.action == AuditAction.SPEC_APPROVED)
    assert approved.before_hash and approved.after_hash and approved.before_hash != approved.after_hash
    assert approved.detail is not None and approved.detail["comment"] == "Rules confirmed with payroll."
    analysed = next(e for e in spec_events if e.action == AuditAction.REQUIREMENT_ANALYZED)
    assert analysed.detail is not None and analysed.detail["provider"] == "fake"

    assert [event.action for event in ambiguity_events] == [AuditAction.AMBIGUITY_RESOLVED]
    assert len(reviews) == 1
    assert reviews[0].decision == ReviewDecision.APPROVE and reviews[0].reviewer == "asha.ba"


def test_missing_cited_policy_blocks_analysis_without_calling_ai(api: TestClient) -> None:
    requirement = create_requirement(api)
    version_id = requirement["versions"][0]["id"]
    with SessionLocal() as db:
        version = db.get(RequirementVersion, uuid.UUID(version_id))
        assert version is not None
        version.policy_ids = ["POL-OT-99@v1"]
        db.commit()
        call_ids = set(db.scalars(select(LlmCall.id)))

    use_ai(api, FailingAI(AssertionError("AI must not run with missing policies")))
    response = analyze(api, version_id)
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"unknown_policy_ids": ["POL-OT-99@v1"]}
    assert api.get(f"/requirement-versions/{version_id}/specs").json() == []
    with SessionLocal() as db:
        assert set(db.scalars(select(LlmCall.id))) == call_ids


def test_malformed_provider_envelope_is_logged_without_storing_a_spec(api: TestClient) -> None:
    class MalformedAI(StubAI):
        def extract_requirement(self, **kwargs: Any) -> Any:
            return None

    requirement = create_requirement(api)
    version_id = requirement["versions"][0]["id"]
    with SessionLocal() as db:
        call_ids = set(db.scalars(select(LlmCall.id)))
    use_ai(api, MalformedAI(RQ014_EXTRACTION_EXAMPLE))
    response = analyze(api, version_id)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_OUTPUT_INVALID"
    assert api.get(f"/requirement-versions/{version_id}/specs").json() == []
    with SessionLocal() as db:
        calls = list(db.scalars(select(LlmCall).where(LlmCall.id.not_in(call_ids))))
        assert len(calls) == 1
        assert calls[0].error_code == "AI_OUTPUT_INVALID"
        assert calls[0].output_hash is None and calls[0].fallback is False


@pytest.mark.parametrize("rule_key", [None, "UNKNOWN_RULE"])
def test_unattributed_grounding_failure_rolls_back_analysis(
    api: TestClient, rule_key: str | None
) -> None:
    requirement, first = analyzed(api)
    version_id = requirement["versions"][0]["id"]

    def malformed_checker(*args: Any) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                code=ValidationCode.V02_UNGROUNDED_SPAN,
                severity=IssueSeverity.BLOCK,
                message="Ungrounded span",
                detail={"rule_key": rule_key},
            )
        ]

    api.app.dependency_overrides[get_spec_checker] = lambda: malformed_checker
    response = analyze(api, version_id)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "INTEGRATION_UNAVAILABLE"
    assert api.get(f"/requirement-versions/{version_id}/specs").json() == [first["spec"]]
    with SessionLocal() as db:
        superseded = db.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_id == uuid.UUID(first["spec"]["id"]),
                AuditEvent.action == AuditAction.SPEC_SUPERSEDED,
            )
        ).all()
        assert superseded == []


def test_checker_exception_rolls_back_analysis_without_exposing_message(api: TestClient) -> None:
    requirement = create_requirement(api)
    version_id = requirement["versions"][0]["id"]

    def failing_checker(*args: Any) -> list[ValidationIssue]:
        raise RuntimeError("private-checker-detail")

    api.app.dependency_overrides[get_spec_checker] = lambda: failing_checker
    response = analyze(api, version_id)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "INTEGRATION_UNAVAILABLE"
    assert "private-checker-detail" not in response.text
    assert api.get(f"/requirement-versions/{version_id}/specs").json() == []
    assert api.get(f"/requirements/{requirement['id']}").json()["status"] == "DRAFT"


def test_developer_cannot_resolve_ambiguities(api: TestClient) -> None:
    _, body = analyzed(api)
    spec = body["spec"]
    response = resolve(
        api, spec["ambiguities"][0]["id"], option_index=0, actor_role="DEVELOPER"
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert api.get(f"/specs/{spec['id']}").json() == spec


def test_workflow_timestamps_keep_utc_offsets_after_reload(api: TestClient) -> None:
    _, body = analyzed(api)
    resolved = resolve(api, body["spec"]["ambiguities"][0]["id"], option_index=0).json()
    assert resolved["ambiguities"][0]["resolved_at"].endswith(("Z", "+00:00"))
    assert api.get(f"/specs/{resolved['id']}").json() == resolved
    approved = approve(api, resolved["id"]).json()
    assert approved["approved_at"].endswith(("Z", "+00:00"))
    assert api.get(f"/specs/{resolved['id']}").json() == approved


def test_openapi_exposes_analysis_and_spec_routes(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert paths["/requirement-versions/{version_id}/analyze"]["post"]["tags"] == ["analysis"]
    assert paths["/ambiguities/{ambiguity_id}/resolve"]["post"]["tags"] == ["analysis"]
    assert paths["/specs/{spec_id}"]["get"]["tags"] == ["specs"]
