"""Docs, OpenAPI and the frontend types must agree with the real API."""

from __future__ import annotations

import re
import types as pytypes
import typing
from enum import Enum
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.core import contracts
from app.main import app
from app.models.requirement import Requirement  # noqa: F401  (ensure models import cleanly)

ROOT = Path(__file__).resolve().parents[2]
DOCS = (ROOT / "docs" / "API_CONTRACTS.md").read_text(encoding="utf-8")
TYPES_TS = (ROOT / "frontend" / "src" / "api" / "types.ts").read_text(encoding="utf-8")
OPENAPI = app.openapi()

HEADING = re.compile(r"^### (GET|POST|PUT|PATCH|DELETE) (/\S*)", re.MULTILINE)


def norm(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def documented() -> dict[tuple[str, str], str]:
    """(METHOD, normalised path) -> the section's text."""
    matches = list(HEADING.finditer(DOCS))
    sections: dict[tuple[str, str], str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(DOCS)
        sections[(match.group(1), norm(match.group(2)))] = DOCS[match.end():end]
    return sections


def served() -> dict[tuple[str, str], dict]:
    return {(method.upper(), norm(path)): op for path, item in OPENAPI["paths"].items() for method, op in item.items()}


# --- Paths ---------------------------------------------------------------------------------------


def test_every_documented_endpoint_is_served() -> None:
    missing = sorted(set(documented()) - set(served()))
    assert missing == [], f"documented but missing from the OpenAPI schema: {missing}"


def test_every_served_endpoint_is_documented() -> None:
    undocumented = sorted(set(served()) - set(documented()))
    assert undocumented == [], f"served but not documented in docs/API_CONTRACTS.md: {undocumented}"


def test_the_required_endpoint_set_exists() -> None:
    required = {
        ("POST", "/requirements"), ("GET", "/requirements"), ("GET", "/requirements/{}"),
        ("POST", "/requirements/{}/versions"), ("GET", "/policies"),
        ("POST", "/requirement-versions/{}/analyze"), ("GET", "/requirement-versions/{}/specs"),
        ("GET", "/specs/{}"), ("POST", "/specs/{}/approve"), ("POST", "/ambiguities/{}/resolve"),
        ("POST", "/specs/{}/design-tests"), ("GET", "/specs/{}/tests"), ("POST", "/tests/review"),
        ("POST", "/runs"), ("GET", "/runs/{}"), ("GET", "/defects"), ("POST", "/specs/{}/impact"),
        ("GET", "/metrics/overview"), ("GET", "/audit"), ("GET", "/health"), ("GET", "/version"),
    }
    assert required <= set(served())


def test_a_documented_path_missing_from_openapi_would_be_detected() -> None:
    """The check above is only useful if it can fail: prove it on a deliberately wrong path."""
    fake = DOCS + "\n### GET /nonexistent/{id} — nothing\n"
    matches = {(m.group(1), norm(m.group(2))) for m in HEADING.finditer(fake)}
    assert ("GET", "/nonexistent/{}") in matches - set(served())


# --- Status codes ------------------------------------------------------------------------------------


def test_documented_error_status_codes_are_declared_by_the_endpoint() -> None:
    problems: list[str] = []
    for key, text in documented().items():
        match = re.search(r"\*\*Errors?:?\*\*:?(.*?)(?:\n\n|\Z)", text, re.DOTALL)
        if not match or key not in served():
            continue
        declared = set(served()[key]["responses"]) | {"500"}
        for code in set(re.findall(r"\b(40[0-9]|409|422|50[0-9])\b", match.group(1))):
            if code not in declared:
                problems.append(f"{key}: docs mention {code}, OpenAPI declares {sorted(declared)}")
    assert problems == []


def test_documented_success_status_codes_match() -> None:
    created = {("POST", "/requirements"), ("POST", "/requirements/{}/versions"), ("POST", "/runs"), ("POST", "/specs/{}/impact")}
    for key, op in served().items():
        if key[1] in ("/openapi.json",):
            continue
        codes = set(op["responses"])
        assert ("201" in codes) == (key in created), f"{key} declares {sorted(codes)}"


# --- Frontend types vs Pydantic models -----------------------------------------------------------------

PAIRS = {
    "Policy": "PolicyResponse", "RequirementVersion": "RequirementVersionResponse",
    "Requirement": "RequirementResponse", "SpecRule": "SpecRuleResponse", "Ambiguity": "AmbiguityResponse",
    "Issue": "ValidationIssue", "Spec": "SpecResponse", "AnalysisMetadata": "AnalysisMetadata",
    "AnalyzeResponse": "AnalyzeRequirementResponse", "ApiErrorBody": "ErrorBody", "Assumption": "Assumption",
    "TestCase": "TestCaseResponse", "Criterion": "CriterionResponse", "DesignTestsResponse": "DesignTestsResponse",
    "TestReviewItem": "TestReviewItem", "TestReviewRefusal": "TestReviewRefusal",
    "TestReviewResponse": "TestReviewResponse", "RunTotals": "RunTotals", "TestResult": "ResultResponse",
    "Run": "RunResponse", "Defect": "DefectResponse", "RuleChange": "RuleChange", "ImpactedTest": "ImpactedTest",
    "ChangeImpact": "ChangeImpactResponse", "RunSummary": "RunSummary", "MetricsOverview": "MetricsOverviewResponse",
    "AuditEvent": "AuditEventResponse", "AuditPage": "AuditPage", "ExpectedResult": "ExpectedResult",
    "TestFixtureInputs": "TestFixtureInputs",
}
# Fields the API never sends / types the frontend deliberately narrows (documented here, not hidden).
IGNORED_FIELDS: dict[str, set[str]] = {"Spec": set()}


def ts_interfaces() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for name, body in re.findall(r"export interface (\w+) \{\n(.*?)\n\}", TYPES_TS, re.DOTALL):
        fields: dict[str, str] = {}
        for line in body.splitlines():
            m = re.match(r"^\s{2}(\w+)(\??):\s*(.+?)\s*$", line)
            if m:
                fields[m.group(1)] = m.group(3) + ("|undefined" if m.group(2) else "")
        result[name] = fields
    return result


def allows_none(annotation: object) -> bool:
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, pytypes.UnionType):
        return type(None) in typing.get_args(annotation)
    return annotation is type(None) or annotation is typing.Any


def top_level_union(ts_type: str) -> list[str]:
    """Split a TypeScript type on top-level ``|`` only (not inside <>, {} or [])."""
    parts, depth, current = [], 0, ""
    for char in ts_type:
        depth += char in "<{[(" 
        depth -= char in ">}])"
        if char == "|" and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char
    return [*parts, current.strip()]


def ts_nullable(ts_type: str) -> bool:
    members = top_level_union(ts_type)
    return "null" in members or "unknown" in members or "undefined" in members


INTERFACES = ts_interfaces()


def test_every_paired_interface_exists_in_types_ts() -> None:
    assert sorted(set(PAIRS) - set(INTERFACES)) == []


def test_nullability_check_ignores_null_inside_nested_types() -> None:
    assert not ts_nullable("Record<string, string | number | boolean | null>")
    assert ts_nullable("string | null") and ts_nullable("unknown") and not ts_nullable("string[]")


@pytest.mark.parametrize("ts_name", sorted(PAIRS))
def test_frontend_interface_matches_the_pydantic_model(ts_name: str) -> None:
    model: type[BaseModel] = getattr(contracts, PAIRS[ts_name]) if hasattr(contracts, PAIRS[ts_name]) else None  # type: ignore[assignment]
    assert model is not None, PAIRS[ts_name]
    ts_fields = INTERFACES[ts_name]
    api_fields = model.model_fields
    assert set(ts_fields) == set(api_fields), (
        f"{ts_name}: only in TS {sorted(set(ts_fields) - set(api_fields))}, "
        f"only in API {sorted(set(api_fields) - set(ts_fields))}")
    for name, field in api_fields.items():
        assert allows_none(field.annotation) == ts_nullable(ts_fields[name]), \
            f"{ts_name}.{name}: API nullable={allows_none(field.annotation)}, TS type '{ts_fields[name]}'"


def test_ai_edge_cases_states_match() -> None:
    api = set(typing.get_args(contracts.DesignTestsResponse.model_fields["ai_edge_cases"].annotation))
    assert set(re.findall(r"'([a-z_]+)'", INTERFACES["DesignTestsResponse"]["ai_edge_cases"])) == api


ENUM_FIELDS = [
    ("Requirement", "status", contracts.RequirementStatus), ("Spec", "status", contracts.SpecStatus),
    ("Ambiguity", "status", contracts.AmbiguityStatus), ("Issue", "severity", contracts.IssueSeverity),
    ("AnalysisMetadata", "mode", contracts.AnalysisMode), ("TestCase", "origin", contracts.TestOrigin),
    ("TestCase", "technique", contracts.TestTechnique), ("TestCase", "assertion", contracts.AssertionTemplate),
    ("TestCase", "status", contracts.TestStatus), ("Run", "status", contracts.RunStatus),
    ("Run", "trigger", contracts.RunTrigger), ("TestResult", "status", contracts.ResultStatus),
    ("Defect", "status", contracts.DefectStatus), ("ImpactedTest", "impact_class", contracts.ImpactClass),
    ("RuleChange", "kind", contracts.RuleChangeKind),
]


@pytest.mark.parametrize(("interface", "field", "enum"), ENUM_FIELDS)
def test_frontend_enum_unions_match_the_backend_enums(interface: str, field: str, enum: type[Enum]) -> None:
    declared = INTERFACES[interface][field]
    aliases = {"TestStatus": contracts.TestStatus, "TestOrigin": contracts.TestOrigin,
               "TestTechnique": contracts.TestTechnique, "Assertion": contracts.AssertionTemplate,
               "ImpactClass": contracts.ImpactClass}
    if declared in aliases:
        alias = re.search(rf"export type {declared} =(.*)", TYPES_TS).group(1)  # type: ignore[union-attr]
        declared = alias
    literals = set(re.findall(r"'([A-Za-z_]+)'", declared))
    assert literals == {member.value for member in enum}, f"{interface}.{field}: {sorted(literals)}"


def test_ids_are_uuids_in_every_response_model() -> None:
    """Every field named id / *_id in a response model is a UUID in the API (strings in TypeScript)."""
    bad: list[str] = []
    for ts_name, model_name in PAIRS.items():
        model = getattr(contracts, model_name)
        for name, field in model.model_fields.items():
            if (name == "id" or name.endswith("_id")) and "UUID" not in str(field.annotation) and name != "trace_id":
                bad.append(f"{model_name}.{name}: {field.annotation}")
    assert bad == []
