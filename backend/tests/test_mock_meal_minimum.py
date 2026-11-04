"""The mock's meal minimum (MOCK_MEAL_MIN, default 30) and its agreement with the oracle."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.schemas import EdgeCaseSuggestion
from app.core.contracts import AssertionTemplate, ExpectedResult, TestInputs
from conftest import MockServer
from flow_helpers import QA, V2, approve_engine_tests, approved_spec, design, failing_codes, point_at, run
from mock_api.calculator import VERSIONS, calculate, meal_minimum
from mock_api.main import app as mock_app
from test_tests_runs_api import SuggestionsAI, use_ai

BODY = {"start_time": "08:00", "end_time": "17:00", "overnight": False}


def paid(meal: int | None, version: str = "1.4.0", minimum: int | None = None) -> int:
    return calculate(version, 8 * 60, 17 * 60, False, meal, minimum)["paid_minutes"]


# --- Unit behaviour -------------------------------------------------------------------------


def test_the_default_minimum_is_30(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOCK_MEAL_MIN", raising=False)
    assert meal_minimum() == 30
    monkeypatch.setenv("MOCK_MEAL_MIN", "")
    assert meal_minimum() == 30


@pytest.mark.parametrize(("meal", "expected_paid"), [(0, 540), (None, 540), (1, 540), (20, 540), (29, 540),
                                                     (30, 510), (45, 495), (60, 480)])
def test_breaks_under_the_minimum_are_not_deducted(meal: int | None, expected_paid: int,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOCK_MEAL_MIN", raising=False)
    assert paid(meal) == expected_paid


@pytest.mark.parametrize("version", sorted(VERSIONS))
def test_every_version_applies_the_minimum(version: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOCK_MEAL_MIN", raising=False)
    assert paid(29, version) == paid(0, version)
    assert paid(30, version) != paid(0, version) or version == "1.3.0"  # 1.3.0 ignores nothing here: daytime shift


def test_the_minimum_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_MEAL_MIN", "0")
    assert paid(15) == 525 and paid(0) == 540
    monkeypatch.setenv("MOCK_MEAL_MIN", "45")
    assert paid(30) == 540 and paid(45) == 495


@pytest.mark.parametrize("bad", ["abc", "-5", "3.5"])
def test_an_invalid_minimum_is_a_configuration_error(bad: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_MEAL_MIN", bad)
    with pytest.raises(ValueError):
        meal_minimum()
    with TestClient(mock_app) as client:
        assert client.get("/version").status_code == 503
        assert client.post("/v1/pay/calculate", json={**BODY, "meal_break_minutes": 30}).status_code == 503


def test_the_http_api_applies_and_reports_the_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOCK_MEAL_MIN", raising=False)
    with TestClient(mock_app) as client:
        try:
            client.post("/admin/version", json={"version": "1.4.0"})
            info = client.get("/version").json()
            assert info["version"] == "1.4.0" and info["meal_minimum"] == 30 and "1.5.0" in info["available"]
            assert client.post("/v1/pay/calculate", json={**BODY, "meal_break_minutes": 29}).json()["paid_minutes"] == 540
            assert client.post("/v1/pay/calculate", json={**BODY, "meal_break_minutes": 30}).json()["paid_minutes"] == 510
            assert client.post("/v1/pay/calculate", json={**BODY, "meal_break_minutes": 0}).json()["paid_minutes"] == 540
            assert client.post("/v1/pay/calculate", json={**BODY, "meal_break_minutes": None}).status_code == 422
            assert client.post("/v1/pay/calculate", json={**BODY, "meal_break_minutes": -1}).status_code == 422
            monkeypatch.setenv("MOCK_MEAL_MIN", "10")
            assert client.get("/version").json()["meal_minimum"] == 10
        finally:
            client.delete("/admin/version")


# --- The seeded-bug table is unchanged ------------------------------------------------------------


@pytest.fixture()
def api(client: TestClient, mock_server: MockServer) -> Iterator[TestClient]:
    mock_server.use("1.4.0")
    point_at(client, mock_server.base_url)
    yield client
    mock_server.reset()


def test_the_defect_table_is_unchanged_by_the_meal_minimum(api: TestClient, mock_server: MockServer) -> None:
    _, spec = approved_spec(api)
    design(api, spec["id"], ai=False)
    approve_engine_tests(api, spec["id"])
    table: dict[str, set[str]] = {}
    for version in ("1.3.0", "1.3.0-b", "1.3.0-c", "1.4.0"):
        mock_server.use(version)
        table[version] = failing_codes(run(api, spec["id"]))
    assert table == {"1.3.0": {"TC-005", "TC-007", "TC-008"}, "1.3.0-b": {"TC-002", "TC-003", "TC-008"},
                     "1.3.0-c": {"TC-005", "TC-006", "TC-008"}, "1.4.0": set()}


def test_version_1_5_0_passes_the_450_specification_and_1_4_0_drifts(api: TestClient, mock_server: MockServer) -> None:
    _, spec = approved_spec(api, V2)
    design(api, spec["id"], ai=False)
    approve_engine_tests(api, spec["id"])
    mock_server.use("1.5.0")
    assert failing_codes(run(api, spec["id"])) == set()
    mock_server.use("1.4.0")
    assert failing_codes(run(api, spec["id"])) == {"TC-003", "TC-008"}


def twenty_minute_break(**overrides: Any) -> EdgeCaseSuggestion:
    values: dict[str, Any] = {
        "title": "Short break", "rationale": "A 20-minute break is below the 30-minute minimum, so it is not deducted.",
        "inputs": TestInputs(start_time="10:00", end_time="19:00", overnight=False, meal_break_minutes=20),
        "assertion": AssertionTemplate.PAID_EQUALS, "claimed_expected": ExpectedResult(paid_minutes=540),
        "rule_keys": ["MEAL_DEDUCTION"]}
    values.update(overrides)
    return EdgeCaseSuggestion(**values)


def test_an_ai_edge_case_with_a_20_minute_break_passes_on_1_4_0(api: TestClient) -> None:
    _, spec = approved_spec(api)
    use_ai(api, SuggestionsAI([twenty_minute_break()]))
    tests = design(api, spec["id"])["tests"]
    ai_test = next(t for t in tests if t["origin"] == "AI")
    assert ai_test["status"] == "DRAFT" and ai_test["issues"] == []
    assert ai_test["expected"]["paid_minutes"] == 540  # the oracle applies the specification's minimum of 30
    approved = api.post("/tests/review", json={**QA, "decision": "APPROVE", "test_ids": [ai_test["id"]]}).json()
    assert approved["reviewed"][0]["new_status"] == "APPROVED"
    body = api.post("/runs", json={**QA, "spec_id": spec["id"], "test_ids": [ai_test["id"]]}).json()
    assert body["sut_version"] == "1.4.0"
    assert [(r["status"], r["observed"]["paid_minutes"]) for r in body["results"]] == [("PASS", 540)]


def test_a_wrong_ai_claim_for_a_short_break_is_blocked(api: TestClient) -> None:
    _, spec = approved_spec(api)
    use_ai(api, SuggestionsAI([twenty_minute_break(claimed_expected=ExpectedResult(paid_minutes=520))]))
    ai_test = next(t for t in design(api, spec["id"])["tests"] if t["origin"] == "AI")
    assert ai_test["status"] == "BLOCKED" and ai_test["expected"]["paid_minutes"] == 540
    assert "V08_AI_CLAIM_MISMATCH" in {i["code"] for i in ai_test["issues"]}
