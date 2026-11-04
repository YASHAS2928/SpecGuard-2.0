"""Quality Engine integration: the real ``check_spec`` and its wiring into the backend."""

from __future__ import annotations

import copy
import inspect
import json
import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.fake_provider import FakeProvider
from app.ai.schemas import AIResult
from app.core.contracts import (
    RQ014_EXTRACTION_EXAMPLE,
    AIProvider,
    IssueSeverity,
    PolicyResponse,
    RequirementExtraction,
    ValidationCode,
    ValidationIssue,
)
from app.core.dependencies import get_ai
from app.database.seed import FICTIONAL_POLICIES
from app.engine import interface
from app.engine.interface import check_spec
from app.services.integration_service import get_spec_checker

TODAY = date(2026, 11, 4)
REQUIREMENT_TEXT = (
    "For an overnight shift, calculate overtime correctly after the employee has worked "
    "the configured number of paid hours, excluding the unpaid meal break."
)
V1 = ("POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1")
V2 = ("POL-OT-01@v2", "POL-MEAL-02@v1", "POL-DATE-03@v1")
BA = {"actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"}


def make_policies(*refs: str) -> list[PolicyResponse]:
    wanted = set(refs)
    return [
        PolicyResponse(
            id=uuid.uuid4(), policy_code=seed.policy_code, version=seed.version,
            ref=f"{seed.policy_code}@v{seed.version}", title=seed.title, rule_text=seed.rule_text,
            effective_from=seed.effective_from, effective_to=seed.effective_to, fictional=True,
        )
        for seed in FICTIONAL_POLICIES
        if f"{seed.policy_code}@v{seed.version}" in wanted
    ]


def extraction(refs: Sequence[str] = V1, requirement_text: str = REQUIREMENT_TEXT) -> RequirementExtraction:
    return FakeProvider().extract_requirement(
        requirement_text=requirement_text, policies=make_policies(*refs)
    ).data


def altered(base: RequirementExtraction, rule_key: str, **changes: Any) -> RequirementExtraction:
    data = base.model_dump(mode="json")
    next(rule for rule in data["rules"] if rule["rule_key"] == rule_key).update(changes)
    return RequirementExtraction.model_validate(data)


def check(base: RequirementExtraction, refs: Sequence[str] = V1, text: str = REQUIREMENT_TEXT,
          policies: list[PolicyResponse] | None = None, today: date = TODAY) -> list[ValidationIssue]:
    return check_spec(base, text, make_policies(*refs) if policies is None else policies, today=today)


def by_code(issues: list[ValidationIssue], code: ValidationCode) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.code == code]


# --- Contract of check_spec ---------------------------------------------------------


@pytest.mark.parametrize("refs", [V1, V2])
def test_the_fake_extraction_is_fully_grounded(refs: Sequence[str]) -> None:
    assert check(extraction(refs), refs) == []


def test_signature_matches_what_the_backend_calls() -> None:
    names = list(inspect.signature(check_spec).parameters)
    assert names[:3] == ["extraction", "requirement_text", "policies"]
    assert inspect.signature(check_spec).parameters["today"].kind is inspect.Parameter.KEYWORD_ONLY


def test_backend_wiring_finds_the_real_checker() -> None:
    assert get_spec_checker() is check_spec


def test_a_tampered_span_is_reported_for_exactly_that_rule() -> None:
    bad = altered(extraction(), "OT_THRESHOLD", source_span="paid minutes above 999 in a single shift are overtime")
    issues = check(bad)
    assert len(issues) == 1 and all(isinstance(issue, ValidationIssue) for issue in issues)
    issue = issues[0]
    assert issue.code == ValidationCode.V02_UNGROUNDED_SPAN and issue.severity == IssueSeverity.BLOCK
    assert issue.detail is not None and issue.detail["rule_key"] == "OT_THRESHOLD"
    assert issue.field_path == "rules.OT_THRESHOLD.source_span"


def test_grounding_is_case_sensitive() -> None:
    shouted = altered(extraction(), "OT_THRESHOLD", source_span="PAID MINUTES ABOVE 480 IN A SINGLE SHIFT ARE OVERTIME")
    assert [i.code for i in check(shouted)] == [ValidationCode.V02_UNGROUNDED_SPAN]


def test_grounding_ignores_whitespace_differences() -> None:
    spaced = "For an\n  overnight   shift, calculate overtime correctly after the employee has worked\tthe configured number of paid hours, excluding the unpaid meal break."
    assert check(extraction(), text=spaced) == []


def test_a_policy_span_must_come_from_the_rules_own_cited_policy() -> None:
    meal_text = "Subtract a 30-minute unpaid meal break when an approved break event is present"
    stolen = altered(extraction(), "OT_THRESHOLD", source_span=meal_text)
    issues = check(stolen)  # the meal policy is attached, but the rule cites the overtime policy
    assert [i.code for i in issues] == [ValidationCode.V02_UNGROUNDED_SPAN]


def test_a_rule_without_policy_ref_is_checked_against_the_requirement_only() -> None:
    from_policy = altered(extraction(), "END_BEFORE_START",
                          source_span="A shift crossing midnight belongs to the same shift instance")
    assert [i.code for i in check(from_policy)] == [ValidationCode.V02_UNGROUNDED_SPAN]


def test_a_rule_may_quote_the_requirement_even_when_it_cites_a_policy() -> None:
    quoted = altered(extraction(), "SHIFT_SPAN", source_span="For an overnight shift")
    assert check(quoted) == []


def test_an_unattached_policy_is_v03_and_the_rule_is_ungrounded() -> None:
    issues = check(extraction(), refs=("POL-MEAL-02@v1", "POL-DATE-03@v1"))
    assert sorted(i.code.value for i in issues) == ["V02_UNGROUNDED_SPAN", "V03_POLICY_UNKNOWN"]
    assert {i.detail["rule_key"] for i in issues if i.detail} == {"OT_THRESHOLD"}


def test_a_blank_span_cannot_reach_the_checker() -> None:
    data = extraction().model_dump(mode="json")
    data["rules"][0]["source_span"] = "   "
    with pytest.raises(ValueError):  # the shared contract already rejects blank spans
        RequirementExtraction.model_validate(data)


# --- V04: expired policies block, upcoming ones do not ----------------------------------


def test_an_expired_policy_blocks_each_rule_citing_it() -> None:
    issues = check(extraction(), today=date(2027, 1, 1))
    expired = by_code(issues, ValidationCode.V04_POLICY_NOT_EFFECTIVE)
    assert len(expired) == 1 and issues == expired
    assert expired[0].severity == IssueSeverity.BLOCK
    assert expired[0].detail is not None
    assert expired[0].detail["rule_key"] == "OT_THRESHOLD" and expired[0].detail["policy_ref"] == "POL-OT-01@v1"


def test_an_upcoming_policy_is_allowed() -> None:
    assert check(extraction(V2), V2, today=TODAY) == []  # POL-OT-01@v2 starts 2027-01-01


def test_the_last_effective_day_is_inclusive() -> None:
    last_day = date(2026, 12, 31)
    assert check(extraction(), today=last_day) == []
    assert len(check(extraction(), today=last_day + timedelta(days=1))) == 1


def test_an_expired_policy_that_no_rule_cites_gives_a_spec_level_issue() -> None:
    uncited = altered(extraction(), "OT_THRESHOLD", policy_ref=None, origin="EXPLICIT",
                      source_span="For an overnight shift")
    issues = check(uncited, today=date(2027, 6, 1))
    assert [i.code for i in issues] == [ValidationCode.V04_POLICY_NOT_EFFECTIVE]
    assert issues[0].field_path is None
    assert issues[0].detail == {"policy_ref": "POL-OT-01@v1", "effective_to": "2026-12-31"}


def test_only_the_agreed_codes_are_ever_returned() -> None:
    data = extraction().model_dump(mode="json")
    for rule in data["rules"]:
        rule["source_span"] = "not present anywhere"
    allowed = {ValidationCode.V02_UNGROUNDED_SPAN, ValidationCode.V03_POLICY_UNKNOWN,
               ValidationCode.V04_POLICY_NOT_EFFECTIVE}
    issues = check(RequirementExtraction.model_validate(data), refs=("POL-MEAL-02@v1",), today=date(2030, 1, 1))
    assert issues and {issue.code for issue in issues} <= allowed
    assert all(issue.severity == IssueSeverity.BLOCK for issue in issues)


def test_check_spec_is_deterministic_and_does_not_mutate_its_input() -> None:
    base = extraction()
    snapshot = copy.deepcopy(base.model_dump(mode="json"))
    policies = make_policies(*V1)
    first = check_spec(base, REQUIREMENT_TEXT, policies, today=date(2027, 1, 1))
    second = check_spec(base, REQUIREMENT_TEXT, policies, today=date(2027, 1, 1))
    assert [i.model_dump(mode="json") for i in first] == [i.model_dump(mode="json") for i in second]
    assert base.model_dump(mode="json") == snapshot


def test_issue_details_are_json_safe_for_storage() -> None:
    issues = check(extraction(), today=date(2027, 1, 1))
    json.dumps([issue.model_dump(mode="json") for issue in issues])


def test_the_module_exposes_the_documented_source_id() -> None:
    assert interface.REQUIREMENT_SOURCE == "requirement"


# --- End to end through the API, with the REAL checker (no overrides) -----------------


class StubAI:
    provider = AIProvider.FAKE
    model = "stub-model"

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def extract_requirement(self, *, requirement_text: str, policies: Sequence[PolicyResponse]) -> AIResult[RequirementExtraction]:
        return AIResult(data=RequirementExtraction.model_validate(self._data), provider=self.provider,
                        model=self.model, prompt_version="stub-1.0", valid_first_try=True)

    def suggest_edge_cases(self, *, spec: Any) -> Any:
        raise NotImplementedError


def create_requirement(client: TestClient, policies: Sequence[str] = V1) -> dict[str, Any]:
    response = client.post("/requirements", json={
        "code": f"RQ-{uuid.uuid4().int % 900000 + 100000}",
        "title": "Overnight overtime with unpaid meal break",
        "text": REQUIREMENT_TEXT, "policy_ids": list(policies), **BA,
    })
    assert response.status_code == 201, response.text
    return response.json()


def analyze(client: TestClient, version_id: str) -> dict[str, Any]:
    response = client.post(f"/requirement-versions/{version_id}/analyze", json=BA)
    assert response.status_code == 200, response.text
    return response.json()


def resolve_first(client: TestClient, spec: dict[str, Any]) -> dict[str, Any]:
    response = client.post(f"/ambiguities/{spec['ambiguities'][0]['id']}/resolve",
                           json={**BA, "option_index": 0})
    assert response.status_code == 200, response.text
    return response.json()


def test_demo_flow_approves_with_the_real_checker(client: TestClient) -> None:
    requirement = create_requirement(client)
    body = analyze(client, requirement["versions"][0]["id"])
    spec = body["spec"]
    assert [rule["grounded"] for rule in spec["rules"]] == [True] * 4
    assert "unavailable" not in (body["analysis"]["message"] or "")

    resolved = resolve_first(client, spec)
    approved = client.post(f"/specs/{spec['id']}/approve", json=BA)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert resolved["open_ambiguities"] == 0
    assert client.get(f"/requirements/{requirement['id']}").json()["status"] == "SPEC_APPROVED"


def test_policy_change_flow_supersedes_with_the_real_checker(client: TestClient) -> None:
    requirement = create_requirement(client)
    first = analyze(client, requirement["versions"][0]["id"])["spec"]
    resolve_first(client, first)
    assert client.post(f"/specs/{first['id']}/approve", json=BA).status_code == 200

    version = client.post(f"/requirements/{requirement['id']}/versions", json={
        "text": REQUIREMENT_TEXT, "policy_ids": list(V2),
        "change_note": "POL-OT-01 v2 lowers the threshold.", **BA})
    assert version.status_code == 201
    second = analyze(client, version.json()["id"])["spec"]
    rules = {rule["rule_key"]: rule for rule in second["rules"]}
    assert rules["OT_THRESHOLD"]["params"]["threshold"] == 450 and rules["OT_THRESHOLD"]["grounded"] is True

    resolve_first(client, second)
    assert client.post(f"/specs/{second['id']}/approve", json=BA).status_code == 200
    assert client.get(f"/specs/{first['id']}").json()["status"] == "SUPERSEDED"


def test_ungrounded_rule_still_blocks_approval_with_the_real_checker(client: TestClient) -> None:
    data = copy.deepcopy(RQ014_EXTRACTION_EXAMPLE)
    data["rules"][0]["source_span"] = "paid minutes above 999 in a single shift are overtime"
    client.app.dependency_overrides[get_ai] = lambda: StubAI(data)  # type: ignore[attr-defined]
    requirement = create_requirement(client)
    spec = analyze(client, requirement["versions"][0]["id"])["spec"]
    assert {rule["rule_key"]: rule["grounded"] for rule in spec["rules"]}["OT_THRESHOLD"] is False
    assert "V02_UNGROUNDED_SPAN" in {issue["code"] for issue in spec["issues"]}

    resolve_first(client, spec)
    response = client.post(f"/specs/{spec['id']}/approve", json=BA)
    assert response.status_code == 409
    details = response.json()["error"]["details"]
    assert details["ungrounded_rules"] == ["OT_THRESHOLD"]
    assert details["blocking_issues"] == ["V02_UNGROUNDED_SPAN"]
