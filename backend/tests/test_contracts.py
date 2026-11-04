"""Contract and error-format tests.

These protect the interfaces shared with the Quality Engine (Member 2), the AI
module (Member 3) and the frontend (Member 4).
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.core.contracts import (
    MODELS_WITH_EXAMPLES,
    RQ014_EXTRACTION_EXAMPLE,
    ChangeImpactRequest,
    DeductionParams,
    ExpectedResult,
    RequirementCreate,
    RequirementExtraction,
    ResolveAmbiguityRequest,
    RunCreateRequest,
    RunTotals,
    SpecPatchOperation,
    TestInputs,
    TestReviewRequest,
    ThresholdRule,
)
from app.core.errors import ConflictError
from app.main import create_app


def _extraction() -> dict[str, Any]:
    return copy.deepcopy(RQ014_EXTRACTION_EXAMPLE)


# --- Examples ------------------------------------------------------------------


@pytest.mark.parametrize("model", MODELS_WITH_EXAMPLES, ids=lambda m: m.__name__)
def test_every_documented_example_is_valid(model: type[BaseModel]) -> None:
    examples = model.model_config.get("json_schema_extra", {}).get("examples", [])
    assert examples, f"{model.__name__} has no examples"
    for example in examples:
        model.model_validate(example)


def test_rq014_extraction_parses_into_typed_rules() -> None:
    extraction = RequirementExtraction.model_validate(_extraction())
    assert [rule.type for rule in extraction.rules] == [
        "THRESHOLD",
        "DEDUCTION",
        "SHIFT_SPAN",
        "VALIDATION",
    ]
    assert isinstance(extraction.rules[0], ThresholdRule)
    assert extraction.rules[1].params.unresolved_fields() == ["min_qualifying"]


# --- AI extraction safety --------------------------------------------------------


def test_unknown_rule_type_is_rejected() -> None:
    data = _extraction()
    data["rules"][0]["type"] = "DOUBLE_TIME"
    with pytest.raises(ValidationError):
        RequirementExtraction.model_validate(data)


def test_unexpected_fields_are_rejected() -> None:
    data = _extraction()
    data["rules"][0]["command"] = "run tests"
    with pytest.raises(ValidationError):
        RequirementExtraction.model_validate(data)


@pytest.mark.parametrize(
    "malicious",
    [
        "import os and delete files",
        "see https://example.com/policy",
        "```python print(1) ```",
        "call eval(payload)",
    ],
)
def test_executable_content_is_rejected_in_ai_text(malicious: str) -> None:
    data = _extraction()
    data["rules"][0]["description"] = malicious
    with pytest.raises(ValidationError):
        RequirementExtraction.model_validate(data)


def test_policy_origin_requires_policy_ref() -> None:
    data = _extraction()
    data["rules"][0]["policy_ref"] = None
    with pytest.raises(ValidationError):
        RequirementExtraction.model_validate(data)


def test_duplicate_rule_keys_are_rejected() -> None:
    data = _extraction()
    data["rules"][1]["rule_key"] = "OT_THRESHOLD"
    with pytest.raises(ValidationError):
        RequirementExtraction.model_validate(data)


def test_ambiguity_must_reference_known_rules() -> None:
    data = _extraction()
    data["ambiguities"][0]["affects_rules"] = ["UNKNOWN_RULE"]
    with pytest.raises(ValidationError):
        RequirementExtraction.model_validate(data)


def test_patch_must_target_known_rule() -> None:
    data = _extraction()
    data["ambiguities"][0]["options"][0]["patch"][0]["path"] = "/rules/GHOST_RULE/params/threshold"
    with pytest.raises(ValidationError):
        RequirementExtraction.model_validate(data)


@pytest.mark.parametrize(
    "path",
    ["/rules/OT_THRESHOLD", "/inputs/0/name", "/rules/OT_THRESHOLD/params/../origin", "/status"],
)
def test_patch_paths_are_restricted(path: str) -> None:
    with pytest.raises(ValidationError):
        SpecPatchOperation(op="replace", path=path, value=1)


def test_patch_string_values_are_restricted() -> None:
    with pytest.raises(ValidationError):
        SpecPatchOperation(op="replace", path="/rules/OT_THRESHOLD/origin", value="x; drop table")
    with pytest.raises(ValidationError):
        SpecPatchOperation(op="add", path="/rules/OT_THRESHOLD/origin", value="CLARIFIED")


def test_unresolved_params_are_reported() -> None:
    assert DeductionParams(min_qualifying=None).unresolved_fields() == ["min_qualifying"]
    assert DeductionParams(min_qualifying=30).unresolved_fields() == []


# --- Request contracts -----------------------------------------------------------


def test_system_role_cannot_act_as_human() -> None:
    example = RequirementCreate.model_config["json_schema_extra"]["examples"][0]
    data = {**example, "actor_role": "SYSTEM"}
    with pytest.raises(ValidationError):
        RequirementCreate.model_validate(data)


def test_requirement_rejects_duplicate_policies() -> None:
    example = RequirementCreate.model_config["json_schema_extra"]["examples"][0]
    data = {**example, "policy_ids": ["POL-OT-01@v1", "POL-OT-01@v1"]}
    with pytest.raises(ValidationError):
        RequirementCreate.model_validate(data)


def test_resolve_requires_exactly_one_choice() -> None:
    base = {"actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"}
    with pytest.raises(ValidationError):
        ResolveAmbiguityRequest.model_validate(base)
    with pytest.raises(ValidationError):
        ResolveAmbiguityRequest.model_validate({**base, "option_index": 0, "defer": True})
    assert ResolveAmbiguityRequest.model_validate({**base, "option_index": 1}).option_index == 1


def test_review_reject_requires_reason_and_unique_ids() -> None:
    base = {"actor": "ravi.qa", "actor_role": "QA_ENGINEER"}
    test_id = "9c4e1d7b-2a63-4f08-b5e9-1a7d3c6f8e12"
    with pytest.raises(ValidationError):
        TestReviewRequest.model_validate({**base, "test_ids": [test_id], "decision": "REJECT"})
    with pytest.raises(ValidationError):
        TestReviewRequest.model_validate(
            {**base, "test_ids": [test_id, test_id], "decision": "APPROVE"}
        )


def test_ids_are_uuids_not_integers() -> None:
    base = {"actor": "ravi.qa", "actor_role": "QA_ENGINEER", "decision": "APPROVE"}
    with pytest.raises(ValidationError):
        TestReviewRequest.model_validate({**base, "test_ids": [1]})
    with pytest.raises(ValidationError):
        TestReviewRequest.model_validate({**base, "test_ids": ["not-a-uuid"]})
    request = TestReviewRequest.model_validate(
        {**base, "test_ids": ["9c4e1d7b-2a63-4f08-b5e9-1a7d3c6f8e12"]}
    )
    assert isinstance(request.test_ids[0], UUID)
    for model in (RunCreateRequest, ChangeImpactRequest):
        with pytest.raises(ValidationError):
            model.model_validate({**base, "spec_id": 3, "from_spec_id": 3})


def test_test_inputs_validate_time_format() -> None:
    with pytest.raises(ValidationError):
        TestInputs(start_time="24:00", end_time="07:00", overnight=True)
    with pytest.raises(ValidationError):
        TestInputs(start_time="9:00", end_time="17:00", overnight=False)


def test_expected_result_rejection_has_no_values() -> None:
    with pytest.raises(ValidationError):
        ExpectedResult(rejects=True, overtime_minutes=0)


def test_run_totals_must_add_up() -> None:
    with pytest.raises(ValidationError):
        RunTotals(total=5, passed=2, failed=1, errors=1)


# --- Standard error format ---------------------------------------------------------


@pytest.fixture()
def error_client() -> Iterator[TestClient]:
    application: FastAPI = create_app()

    @application.get("/_test/conflict")
    def _conflict() -> None:
        raise ConflictError("Specification 3 is already approved.", details={"spec_id": 3})

    @application.post("/_test/requirements")
    def _create(body: RequirementCreate) -> dict[str, str]:
        return {"code": body.code}

    with TestClient(application) as test_client:
        yield test_client


def test_unknown_route_returns_standard_error(error_client: TestClient) -> None:
    response = error_client.get("/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["trace_id"] == response.headers["X-Trace-ID"]


def test_api_error_returns_standard_shape(error_client: TestClient) -> None:
    response = error_client.get("/_test/conflict", headers={"X-Trace-ID": "trace-409"})
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "CONFLICT",
            "message": "Specification 3 is already approved.",
            "details": {"spec_id": 3},
            "trace_id": "trace-409",
        }
    }


def test_request_validation_error_shape(error_client: TestClient) -> None:
    response = error_client.post(
        "/_test/requirements",
        json={"code": "BAD", "title": "x", "text": "short", "policy_ids": [], "actor": "a", "actor_role": "QA_ENGINEER"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    locations = {tuple(item["loc"]) for item in error["details"]}
    assert ("body", "code") in locations
    assert ("body", "policy_ids") in locations
    assert all("input" not in item for item in error["details"])
