"""Shared Pydantic v2 contracts for SpecGuard 2.0.

Every request body, response body and AI output used across the backend is
defined here. Member 2 (Quality Engine), Member 3 (AI) and the frontend all
build against these models.

Safety properties enforced at the contract level:
* All models forbid unknown fields.
* Rule types and parameters are a closed, typed set (discriminated union).
* AI-written text rejects URLs, code fences and executable statements.
* Clarification patches may only replace a rule parameter or origin with a scalar.
* The SYSTEM role cannot perform human approval or review actions.

All workforce policies referenced in examples are fictional.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Patterns and reusable constrained types
# ---------------------------------------------------------------------------

REQUIREMENT_CODE_PATTERN = r"^RQ-\d{3,6}$"
POLICY_CODE_PATTERN = r"^POL-[A-Z]{2,10}-\d{2}$"
POLICY_REF_PATTERN = r"^POL-[A-Z]{2,10}-\d{2}@v\d{1,3}$"
RULE_KEY_PATTERN = r"^[A-Z][A-Z0-9_]{2,40}$"
AMBIGUITY_CODE_PATTERN = r"^AMB-\d{1,3}$"
CRITERION_CODE_PATTERN = r"^AC-\d{1,4}$"
TEST_CODE_PATTERN = r"^TC-\d{1,5}$"
TIME_HHMM_PATTERN = r"^(?:[01]\d|2[0-3]):[0-5]\d$"
SHA256_HEX_PATTERN = r"^[0-9a-f]{64}$"
PATCH_PATH_PATTERN = r"^/rules/[A-Z][A-Z0-9_]{2,40}/(?:params/[a-z_]{2,40}|origin)$"
PATCH_STRING_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

_EXECUTABLE_CONTENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"```"),
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"\bimport\s+[A-Za-z_]"),
    re.compile(r"__import__|\bexec\s*\(|\beval\s*\(|\bsubprocess\b|\bos\.system\b"),
    re.compile(r"\b(?:rm|del)\s+-[a-z]", re.IGNORECASE),
)


def reject_executable_content(value: str) -> str:
    """Reject AI-written text that contains URLs, code fences or executable statements."""
    for pattern in _EXECUTABLE_CONTENT_PATTERNS:
        if pattern.search(value):
            raise ValueError(
                "Text must not contain URLs, code blocks or executable statements."
            )
    return value


RequirementCode = Annotated[str, StringConstraints(pattern=REQUIREMENT_CODE_PATTERN)]
PolicyCode = Annotated[str, StringConstraints(pattern=POLICY_CODE_PATTERN)]
PolicyRef = Annotated[str, StringConstraints(pattern=POLICY_REF_PATTERN)]
RuleKey = Annotated[str, StringConstraints(pattern=RULE_KEY_PATTERN)]
AmbiguityCode = Annotated[str, StringConstraints(pattern=AMBIGUITY_CODE_PATTERN)]
CriterionCode = Annotated[str, StringConstraints(pattern=CRITERION_CODE_PATTERN)]
TestCode = Annotated[str, StringConstraints(pattern=TEST_CODE_PATTERN)]
TimeHHMM = Annotated[str, StringConstraints(pattern=TIME_HHMM_PATTERN)]
Sha256Hex = Annotated[str, StringConstraints(pattern=SHA256_HEX_PATTERN)]
ActorName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]

AIText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    AfterValidator(reject_executable_content),
]
ShortAIText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(reject_executable_content),
]
SourceSpan = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=500),
    AfterValidator(reject_executable_content),
]

ScalarValue = Union[StrictBool, StrictInt, StrictStr, None]


class ContractModel(BaseModel):
    """Base model for all contracts: strict about unknown fields, ORM-friendly."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        from_attributes=True,
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AIProvider(StrEnum):
    GROQ = "groq"
    GEMINI = "gemini"
    FAKE = "fake"


class ActorRole(StrEnum):
    BUSINESS_ANALYST = "BUSINESS_ANALYST"
    QA_ENGINEER = "QA_ENGINEER"
    DEVELOPER = "DEVELOPER"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"


class RequirementStatus(StrEnum):
    DRAFT = "DRAFT"
    ANALYZED = "ANALYZED"
    SPEC_APPROVED = "SPEC_APPROVED"
    CHANGED = "CHANGED"


class SpecStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"


class RuleType(StrEnum):
    THRESHOLD = "THRESHOLD"
    DEDUCTION = "DEDUCTION"
    SHIFT_SPAN = "SHIFT_SPAN"
    VALIDATION = "VALIDATION"


class RuleOrigin(StrEnum):
    EXPLICIT = "EXPLICIT"
    POLICY = "POLICY"
    ASSUMED = "ASSUMED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    CLARIFIED = "CLARIFIED"


class InputType(StrEnum):
    TIME_HHMM = "time_hhmm"
    BOOL = "bool"
    INT_OR_NULL = "int_or_null"


class ValidationCheck(StrEnum):
    END_BEFORE_START_WITHOUT_OVERNIGHT = "END_BEFORE_START_WITHOUT_OVERNIGHT"
    OVERNIGHT_WITHOUT_MIDNIGHT_CROSSING = "OVERNIGHT_WITHOUT_MIDNIGHT_CROSSING"
    NEGATIVE_BREAK = "NEGATIVE_BREAK"
    BREAK_EXCEEDS_SHIFT = "BREAK_EXCEEDS_SHIFT"


class AmbiguityStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DEFERRED = "DEFERRED"


class AnalysisMode(StrEnum):
    LLM = "llm"
    FAKE = "fake"
    MANUAL_REQUIRED = "manual_required"


class TestOrigin(StrEnum):
    ENGINE = "ENGINE"
    AI = "AI"


class TestTechnique(StrEnum):
    BOUNDARY = "BOUNDARY"
    PARTITION = "PARTITION"
    DECISION = "DECISION"
    NEGATIVE = "NEGATIVE"
    EDGE = "EDGE"


class AssertionTemplate(StrEnum):
    PAID_EQUALS = "PAID_EQUALS"
    OT_EQUALS = "OT_EQUALS"
    REJECTS = "REJECTS"


class TestStatus(StrEnum):
    DRAFT = "DRAFT"
    BLOCKED = "BLOCKED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    STALE = "STALE"
    OBSOLETE = "OBSOLETE"


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class RunTrigger(StrEnum):
    MANUAL = "MANUAL"
    IMPACT_RERUN = "IMPACT_RERUN"


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ResultStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


class DefectStatus(StrEnum):
    OPEN = "OPEN"
    FIXED = "FIXED"
    VERIFIED = "VERIFIED"


class IssueSeverity(StrEnum):
    BLOCK = "BLOCK"
    WARN = "WARN"


class ValidationCode(StrEnum):
    V01_SCHEMA = "V01_SCHEMA"
    V02_UNGROUNDED_SPAN = "V02_UNGROUNDED_SPAN"
    V03_POLICY_UNKNOWN = "V03_POLICY_UNKNOWN"
    V04_POLICY_NOT_EFFECTIVE = "V04_POLICY_NOT_EFFECTIVE"
    V05_UNSUPPORTED_RULE = "V05_UNSUPPORTED_RULE"
    V06_TRACE_BROKEN = "V06_TRACE_BROKEN"
    V07_ORACLE_ERROR = "V07_ORACLE_ERROR"
    V08_AI_CLAIM_MISMATCH = "V08_AI_CLAIM_MISMATCH"
    V09_DUPLICATE = "V09_DUPLICATE"
    V10_COVERAGE_GAP = "V10_COVERAGE_GAP"
    V11_INJECTION_SUSPECT = "V11_INJECTION_SUSPECT"
    V12_FORBIDDEN_TARGET = "V12_FORBIDDEN_TARGET"
    V13_UNRESOLVED_PARAMETER = "V13_UNRESOLVED_PARAMETER"


class EntityType(StrEnum):
    REQUIREMENT = "REQUIREMENT"
    REQUIREMENT_VERSION = "REQUIREMENT_VERSION"
    SPEC = "SPEC"
    RULE = "RULE"
    AMBIGUITY = "AMBIGUITY"
    CRITERION = "CRITERION"
    TEST_CASE = "TEST_CASE"
    RUN = "RUN"
    RESULT = "RESULT"
    DEFECT = "DEFECT"
    CHANGE_IMPACT = "CHANGE_IMPACT"


class AuditAction(StrEnum):
    REQUIREMENT_CREATED = "REQUIREMENT_CREATED"
    REQUIREMENT_VERSION_CREATED = "REQUIREMENT_VERSION_CREATED"
    REQUIREMENT_ANALYZED = "REQUIREMENT_ANALYZED"
    AMBIGUITY_RESOLVED = "AMBIGUITY_RESOLVED"
    AMBIGUITY_DEFERRED = "AMBIGUITY_DEFERRED"
    SPEC_APPROVED = "SPEC_APPROVED"
    SPEC_SUPERSEDED = "SPEC_SUPERSEDED"
    TESTS_DESIGNED = "TESTS_DESIGNED"
    TEST_APPROVED = "TEST_APPROVED"
    TEST_REJECTED = "TEST_REJECTED"
    RUN_EXECUTED = "RUN_EXECUTED"
    DEFECT_UPDATED = "DEFECT_UPDATED"
    CHANGE_IMPACT_ANALYZED = "CHANGE_IMPACT_ANALYZED"


class ImpactClass(StrEnum):
    STALE_EXPECTED = "STALE_EXPECTED"
    OBSOLETE = "OBSOLETE"
    NEW = "NEW"
    UNAFFECTED = "UNAFFECTED"


class RuleChangeKind(StrEnum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    PARAM_CHANGED = "PARAM_CHANGED"
    POLICY_VERSION_CHANGED = "POLICY_VERSION_CHANGED"


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    STATE_TRANSITION_NOT_ALLOWED = "STATE_TRANSITION_NOT_ALLOWED"
    SPEC_NOT_APPROVABLE = "SPEC_NOT_APPROVABLE"
    TEST_NOT_APPROVABLE = "TEST_NOT_APPROVABLE"
    AI_PROVIDER_NOT_CONFIGURED = "AI_PROVIDER_NOT_CONFIGURED"
    AI_PROVIDER_ERROR = "AI_PROVIDER_ERROR"
    AI_OUTPUT_INVALID = "AI_OUTPUT_INVALID"
    INTEGRATION_UNAVAILABLE = "INTEGRATION_UNAVAILABLE"
    HTTP_ERROR = "HTTP_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# Shared actor fields
# ---------------------------------------------------------------------------


class ActorFields(ContractModel):
    """Identifies the human performing an action. MVP has no authentication."""

    actor: ActorName
    actor_role: ActorRole

    @field_validator("actor_role")
    @classmethod
    def _human_roles_only(cls, value: ActorRole) -> ActorRole:
        if value == ActorRole.SYSTEM:
            raise ValueError("The SYSTEM role cannot perform human actions.")
        return value


# ---------------------------------------------------------------------------
# Validation issues and errors
# ---------------------------------------------------------------------------


class ValidationIssue(ContractModel):
    """A deterministic validation finding (produced by the Quality Engine or backend)."""

    code: ValidationCode
    severity: IssueSeverity
    entity_type: EntityType | None = None
    entity_id: UUID | None = None
    message: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    field_path: Annotated[str, StringConstraints(max_length=200)] | None = None
    detail: dict[str, Any] | None = None


class ErrorBody(ContractModel):
    code: ErrorCode
    message: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    details: Any = None
    trace_id: str | None = None


class ErrorResponse(ContractModel):
    """Standard error envelope returned by every endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": {
                        "code": "SPEC_NOT_APPROVABLE",
                        "message": "Specification 3 cannot be approved yet.",
                        "details": {"open_ambiguities": ["AMB-1"], "unresolved_params": []},
                        "trace_id": "demo-trace-001",
                    }
                }
            ]
        }
    )

    error: ErrorBody


# ---------------------------------------------------------------------------
# Policies and requirements
# ---------------------------------------------------------------------------


class PolicyResponse(ContractModel):
    id: UUID
    policy_code: PolicyCode
    version: int = Field(ge=1)
    ref: PolicyRef
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    rule_text: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    effective_from: date
    effective_to: date | None = None
    fictional: bool = True


def _unique_policy_refs(values: list[str]) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError("policy_ids must not contain duplicates.")
    return values


class RequirementCreate(ActorFields):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "code": "RQ-014",
                    "title": "Overnight overtime with unpaid meal break",
                    "text": (
                        "For an overnight shift, calculate overtime correctly after the "
                        "employee has worked the configured number of paid hours, "
                        "excluding the unpaid meal break."
                    ),
                    "policy_ids": ["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"],
                    "actor": "asha.ba",
                    "actor_role": "BUSINESS_ANALYST",
                }
            ]
        }
    )

    code: RequirementCode
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=4000)]
    policy_ids: list[PolicyRef] = Field(min_length=1, max_length=10)

    @field_validator("policy_ids")
    @classmethod
    def _unique_policies(cls, value: list[str]) -> list[str]:
        return _unique_policy_refs(value)


class RequirementVersionCreate(ActorFields):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": (
                        "For an overnight shift, calculate overtime correctly after the "
                        "employee has worked the configured number of paid hours, "
                        "excluding the unpaid meal break."
                    ),
                    "policy_ids": ["POL-OT-01@v2", "POL-MEAL-02@v1", "POL-DATE-03@v1"],
                    "change_note": "POL-OT-01 v2 lowers the overtime threshold to 450 minutes.",
                    "actor": "asha.ba",
                    "actor_role": "BUSINESS_ANALYST",
                }
            ]
        }
    )

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=4000)]
    policy_ids: list[PolicyRef] = Field(min_length=1, max_length=10)
    change_note: Comment | None = None

    @field_validator("policy_ids")
    @classmethod
    def _unique_policies(cls, value: list[str]) -> list[str]:
        return _unique_policy_refs(value)


class RequirementVersionResponse(ContractModel):
    id: UUID
    requirement_id: UUID
    version: int = Field(ge=1)
    text: str
    policy_ids: list[PolicyRef]
    author: ActorName
    change_note: str | None = None
    created_at: datetime


class RequirementResponse(ContractModel):
    id: UUID
    code: RequirementCode
    title: str
    status: RequirementStatus
    latest_version: int = Field(ge=1)
    versions: list[RequirementVersionResponse]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AI extraction output (shared by Groq, Gemini and Fake providers)
# ---------------------------------------------------------------------------


class RuleParamsBase(ContractModel):
    """Base for typed rule parameters. ``None`` means the value is unresolved."""

    def unresolved_fields(self) -> list[str]:
        """Return parameter names that still need clarification."""
        return [name for name, value in self if value is None]


class ThresholdParams(RuleParamsBase):
    metric: Literal["paid_minutes"] = "paid_minutes"
    threshold: int | None = Field(default=None, ge=0, le=1440)
    comparison: Literal["gt", "gte"] | None = None
    scope: Literal["per_shift"] | None = None
    output: Literal["overtime_minutes"] = "overtime_minutes"


class DeductionParams(RuleParamsBase):
    field: Literal["meal_break_minutes"] = "meal_break_minutes"
    deduct_if: Literal["recorded"] = "recorded"
    min_qualifying: int | None = Field(default=None, ge=0, le=240)


class ShiftSpanParams(RuleParamsBase):
    midnight_crossing: Literal["same_shift"] = "same_shift"
    requires_overnight_flag: bool | None = None


class ValidationParams(RuleParamsBase):
    check: ValidationCheck
    on_violation: Literal["REJECT"] = "REJECT"


class RuleBase(ContractModel):
    rule_key: RuleKey
    origin: RuleOrigin
    policy_ref: PolicyRef | None = None
    source_span: SourceSpan
    description: ShortAIText | None = None

    @model_validator(mode="after")
    def _policy_origin_needs_ref(self) -> "RuleBase":
        if self.origin == RuleOrigin.POLICY and self.policy_ref is None:
            raise ValueError("Rules with origin POLICY must include policy_ref.")
        return self


class ThresholdRule(RuleBase):
    type: Literal["THRESHOLD"]
    params: ThresholdParams


class DeductionRule(RuleBase):
    type: Literal["DEDUCTION"]
    params: DeductionParams


class ShiftSpanRule(RuleBase):
    type: Literal["SHIFT_SPAN"]
    params: ShiftSpanParams


class ValidationRule(RuleBase):
    type: Literal["VALIDATION"]
    params: ValidationParams


ExtractedRule = Annotated[
    Union[ThresholdRule, DeductionRule, ShiftSpanRule, ValidationRule],
    Field(discriminator="type"),
]

_INPUT_TYPES: dict[str, InputType] = {
    "start_time": InputType.TIME_HHMM,
    "end_time": InputType.TIME_HHMM,
    "overnight": InputType.BOOL,
    "meal_break_minutes": InputType.INT_OR_NULL,
}

SpecOutputName = Literal["paid_minutes", "overtime_minutes"]


class SpecInput(ContractModel):
    name: Literal["start_time", "end_time", "overnight", "meal_break_minutes"]
    type: InputType

    @model_validator(mode="after")
    def _type_matches_name(self) -> "SpecInput":
        expected = _INPUT_TYPES[self.name]
        if self.type != expected:
            raise ValueError(f"Input '{self.name}' must have type '{expected.value}'.")
        return self


class SpecPatchOperation(ContractModel):
    """A restricted patch that a clarification option applies to the draft spec."""

    op: Literal["replace"]
    path: Annotated[str, StringConstraints(pattern=PATCH_PATH_PATTERN)]
    value: ScalarValue

    @field_validator("value")
    @classmethod
    def _safe_string_values(cls, value: ScalarValue) -> ScalarValue:
        if isinstance(value, str) and not PATCH_STRING_VALUE_PATTERN.fullmatch(value):
            raise ValueError("String patch values may contain only letters, digits, '_' and '-'.")
        return value

    @property
    def rule_key(self) -> str:
        """Rule key addressed by this patch (second path segment)."""
        return self.path.split("/")[2]


class ClarificationOption(ContractModel):
    label: ShortAIText
    patch: list[SpecPatchOperation] = Field(min_length=1, max_length=5)


class Ambiguity(ContractModel):
    amb_code: AmbiguityCode
    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=5, max_length=300),
        AfterValidator(reject_executable_content),
    ]
    why: AIText
    affects_rules: list[RuleKey] = Field(min_length=1, max_length=5)
    options: list[ClarificationOption] = Field(min_length=2, max_length=4)


class Assumption(ContractModel):
    text: AIText
    origin: Literal["ASSUMED"] = "ASSUMED"


RQ014_EXTRACTION_EXAMPLE: dict[str, Any] = {
    "inputs": [
        {"name": "start_time", "type": "time_hhmm"},
        {"name": "end_time", "type": "time_hhmm"},
        {"name": "overnight", "type": "bool"},
        {"name": "meal_break_minutes", "type": "int_or_null"},
    ],
    "outputs": ["paid_minutes", "overtime_minutes"],
    "rules": [
        {
            "rule_key": "OT_THRESHOLD",
            "type": "THRESHOLD",
            "params": {
                "metric": "paid_minutes",
                "threshold": 480,
                "comparison": "gt",
                "scope": "per_shift",
                "output": "overtime_minutes",
            },
            "origin": "POLICY",
            "policy_ref": "POL-OT-01@v1",
            "source_span": "paid minutes above 480 in a single shift are overtime",
        },
        {
            "rule_key": "MEAL_DEDUCTION",
            "type": "DEDUCTION",
            "params": {
                "field": "meal_break_minutes",
                "deduct_if": "recorded",
                "min_qualifying": None,
            },
            "origin": "NEEDS_CLARIFICATION",
            "policy_ref": "POL-MEAL-02@v1",
            "source_span": (
                "Subtract a 30-minute unpaid meal break when an approved break event is present"
            ),
        },
        {
            "rule_key": "SHIFT_SPAN",
            "type": "SHIFT_SPAN",
            "params": {"midnight_crossing": "same_shift", "requires_overnight_flag": True},
            "origin": "POLICY",
            "policy_ref": "POL-DATE-03@v1",
            "source_span": "A shift crossing midnight belongs to the same shift instance",
        },
        {
            "rule_key": "END_BEFORE_START",
            "type": "VALIDATION",
            "params": {"check": "END_BEFORE_START_WITHOUT_OVERNIGHT", "on_violation": "REJECT"},
            "origin": "ASSUMED",
            "policy_ref": None,
            "source_span": "For an overnight shift",
        },
    ],
    "ambiguities": [
        {
            "amb_code": "AMB-1",
            "question": "If the recorded meal break is shorter than 30 minutes, is it deducted?",
            "why": "POL-MEAL-02 names a 30-minute break but does not cover partial breaks.",
            "affects_rules": ["MEAL_DEDUCTION"],
            "options": [
                {
                    "label": "Deduct only breaks of 30 minutes or more",
                    "patch": [
                        {
                            "op": "replace",
                            "path": "/rules/MEAL_DEDUCTION/params/min_qualifying",
                            "value": 30,
                        },
                        {"op": "replace", "path": "/rules/MEAL_DEDUCTION/origin", "value": "CLARIFIED"},
                    ],
                },
                {
                    "label": "Deduct whatever break length was recorded",
                    "patch": [
                        {
                            "op": "replace",
                            "path": "/rules/MEAL_DEDUCTION/params/min_qualifying",
                            "value": 0,
                        },
                        {"op": "replace", "path": "/rules/MEAL_DEDUCTION/origin", "value": "CLARIFIED"},
                    ],
                },
            ],
        }
    ],
    "assumptions": [
        {"text": "All times are in one local timezone; daylight-saving changes are out of scope."}
    ],
}


class RequirementExtraction(ContractModel):
    """Structured output every AI provider must return for requirement analysis."""

    model_config = ConfigDict(json_schema_extra={"examples": [RQ014_EXTRACTION_EXAMPLE]})

    inputs: list[SpecInput] = Field(min_length=1, max_length=10)
    outputs: list[SpecOutputName] = Field(min_length=1, max_length=2)
    rules: list[ExtractedRule] = Field(min_length=1, max_length=20)
    ambiguities: list[Ambiguity] = Field(default_factory=list, max_length=10)
    assumptions: list[Assumption] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _cross_references_are_consistent(self) -> "RequirementExtraction":
        rule_keys = [rule.rule_key for rule in self.rules]
        if len(set(rule_keys)) != len(rule_keys):
            raise ValueError("rule_key values must be unique.")
        input_names = [item.name for item in self.inputs]
        if len(set(input_names)) != len(input_names):
            raise ValueError("Input names must be unique.")
        amb_codes = [amb.amb_code for amb in self.ambiguities]
        if len(set(amb_codes)) != len(amb_codes):
            raise ValueError("amb_code values must be unique.")

        known = set(rule_keys)
        for amb in self.ambiguities:
            unknown = set(amb.affects_rules) - known
            if unknown:
                raise ValueError(f"{amb.amb_code} references unknown rules: {sorted(unknown)}")
            for option in amb.options:
                for op in option.patch:
                    if op.rule_key not in known:
                        raise ValueError(
                            f"{amb.amb_code} patch targets unknown rule '{op.rule_key}'."
                        )
        return self


# ---------------------------------------------------------------------------
# Analysis, specs, ambiguities
# ---------------------------------------------------------------------------


class AnalyzeRequirementRequest(ActorFields):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"actor": "asha.ba", "actor_role": "BUSINESS_ANALYST", "force": False}]
        }
    )

    force: bool = False


class AnalysisMetadata(ContractModel):
    """How the analysis was produced. A fake or manual result is never labelled as LLM."""

    mode: AnalysisMode
    provider: AIProvider
    model: str | None = None
    prompt_version: str
    valid_first_try: bool
    retries: int = Field(ge=0)
    fallback_used: bool
    latency_ms: int | None = Field(default=None, ge=0)
    llm_call_id: UUID | None = None
    message: str | None = None


class SpecRuleResponse(ContractModel):
    id: UUID
    rule_key: RuleKey
    type: RuleType
    params: dict[str, Any]
    origin: RuleOrigin
    policy_ref: PolicyRef | None = None
    source_span: str
    description: str | None = None
    grounded: bool | None = None
    unresolved_params: list[str] = Field(default_factory=list)


class AmbiguityResponse(ContractModel):
    id: UUID
    spec_id: UUID
    amb_code: AmbiguityCode
    question: str
    why: str
    affects_rules: list[RuleKey]
    options: list[ClarificationOption]
    status: AmbiguityStatus
    chosen_option_index: int | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None


class SpecResponse(ContractModel):
    id: UUID
    requirement_version_id: UUID
    version: int = Field(ge=1)
    status: SpecStatus
    inputs: list[SpecInput]
    outputs: list[SpecOutputName]
    rules: list[SpecRuleResponse]
    ambiguities: list[AmbiguityResponse]
    assumptions: list[Assumption]
    issues: list[ValidationIssue] = Field(default_factory=list)
    open_ambiguities: int = Field(ge=0)
    blocking_issue_count: int = Field(ge=0)
    parent_spec_id: UUID | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime


class AnalyzeRequirementResponse(ContractModel):
    spec: SpecResponse
    analysis: AnalysisMetadata


class ResolveAmbiguityRequest(ActorFields):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"option_index": 0, "defer": False, "actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"},
                {
                    "option_index": None,
                    "defer": True,
                    "comment": "Waiting for payroll owner.",
                    "actor": "asha.ba",
                    "actor_role": "BUSINESS_ANALYST",
                },
            ]
        }
    )

    option_index: int | None = Field(default=None, ge=0, le=3)
    defer: bool = False
    comment: Comment | None = None

    @model_validator(mode="after")
    def _exactly_one_choice(self) -> "ResolveAmbiguityRequest":
        if self.defer and self.option_index is not None:
            raise ValueError("Provide either option_index or defer=true, not both.")
        if not self.defer and self.option_index is None:
            raise ValueError("Provide option_index, or set defer=true.")
        return self


class ApproveSpecRequest(ActorFields):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "actor": "asha.ba",
                    "actor_role": "BUSINESS_ANALYST",
                    "comment": "Rules confirmed with payroll.",
                }
            ]
        }
    )

    comment: Comment | None = None


# ---------------------------------------------------------------------------
# Criteria and test cases
# ---------------------------------------------------------------------------


class CriterionResponse(ContractModel):
    id: UUID
    spec_id: UUID
    crit_code: CriterionCode
    rule_key: RuleKey
    given: str
    when: str
    then: str


class TestInputs(ContractModel):
    """Fixture inputs sent to the mock Time-to-Pay API."""

    start_time: TimeHHMM
    end_time: TimeHHMM
    overnight: bool
    meal_break_minutes: int | None = Field(default=None, ge=0, le=1440)


class ExpectedResult(ContractModel):
    """Expected (or observed) outcome. Only the oracle sets expected values."""

    paid_minutes: int | None = Field(default=None, ge=0, le=2880)
    overtime_minutes: int | None = Field(default=None, ge=0, le=2880)
    rejects: bool = False

    @model_validator(mode="after")
    def _rejection_has_no_values(self) -> "ExpectedResult":
        if self.rejects and (self.paid_minutes is not None or self.overtime_minutes is not None):
            raise ValueError("A rejection outcome cannot include paid or overtime minutes.")
        return self


class TestCaseResponse(ContractModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "9c4e1d7b-2a63-4f08-b5e9-1a7d3c6f8e12",
                    "spec_id": "3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01",
                    "tc_code": "TC-012",
                    "origin": "ENGINE",
                    "technique": "BOUNDARY",
                    "inputs": {
                        "start_time": "22:00",
                        "end_time": "07:01",
                        "overnight": True,
                        "meal_break_minutes": 60,
                    },
                    "assertion": "OT_EQUALS",
                    "expected": {"paid_minutes": None, "overtime_minutes": 1, "rejects": False},
                    "ai_claimed_expected": None,
                    "rationale": "Paid minutes = 481: just above the threshold.",
                    "risk_score": 7,
                    "status": "DRAFT",
                    "rule_keys": ["OT_THRESHOLD", "SHIFT_SPAN", "MEAL_DEDUCTION"],
                    "criterion_codes": ["AC-1"],
                    "policy_refs": ["POL-OT-01@v1"],
                    "issues": [],
                    "supersedes_id": None,
                    "created_at": "2026-11-04T10:15:00Z",
                }
            ]
        }
    )

    id: UUID
    spec_id: UUID
    tc_code: TestCode
    origin: TestOrigin
    technique: TestTechnique
    inputs: TestInputs
    assertion: AssertionTemplate
    expected: ExpectedResult
    ai_claimed_expected: ExpectedResult | None = None
    rationale: Annotated[str, StringConstraints(max_length=500)]
    risk_score: int | None = Field(default=None, ge=0, le=20)
    status: TestStatus
    rule_keys: list[RuleKey]
    criterion_codes: list[CriterionCode]
    policy_refs: list[PolicyRef]
    issues: list[ValidationIssue] = Field(default_factory=list)
    supersedes_id: UUID | None = None
    created_at: datetime


class DesignTestsRequest(ActorFields):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"actor": "ravi.qa", "actor_role": "QA_ENGINEER", "include_ai_edge_cases": True}
            ]
        }
    )

    include_ai_edge_cases: bool = True


class DesignTestsResponse(ContractModel):
    spec_id: UUID
    criteria: list[CriterionResponse]
    tests: list[TestCaseResponse]
    counts_by_technique: dict[TestTechnique, int]
    blocked_count: int = Field(ge=0)
    ai_edge_cases: Literal["generated", "unavailable", "disabled"]
    ai_message: str | None = None


class TestReviewRequest(ActorFields):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "test_ids": [
                        "5e2a8c13-9b47-4d60-a1f2-6c3e0d9b7a10",
                        "7d9b3f25-1e84-4c7a-8b06-2f5a9e1c4d11",
                        "9c4e1d7b-2a63-4f08-b5e9-1a7d3c6f8e12",
                    ],
                    "decision": "APPROVE",
                    "actor": "ravi.qa",
                    "actor_role": "QA_ENGINEER",
                },
                {
                    "test_ids": ["c8a1e5f3-6d92-4b17-9e40-3b7c5a2d8f27"],
                    "decision": "REJECT",
                    "reason": "Duplicates TC-012.",
                    "actor": "ravi.qa",
                    "actor_role": "QA_ENGINEER",
                },
            ]
        }
    )

    test_ids: list[UUID] = Field(min_length=1, max_length=200)
    decision: ReviewDecision
    reason: Comment | None = None

    @field_validator("test_ids")
    @classmethod
    def _unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("test_ids must not contain duplicates.")
        return value

    @model_validator(mode="after")
    def _reject_needs_reason(self) -> "TestReviewRequest":
        if self.decision == ReviewDecision.REJECT and not self.reason:
            raise ValueError("A reason is required when rejecting tests.")
        return self


class TestReviewItem(ContractModel):
    test_id: UUID
    tc_code: TestCode
    previous_status: TestStatus
    new_status: TestStatus


class TestReviewRefusal(ContractModel):
    test_id: UUID
    code: ErrorCode
    message: str


class TestReviewResponse(ContractModel):
    decision: ReviewDecision
    reviewed: list[TestReviewItem]
    refused: list[TestReviewRefusal]


# ---------------------------------------------------------------------------
# Runs, results and defects
# ---------------------------------------------------------------------------


class RunCreateRequest(ActorFields):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"spec_id": "3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01", "test_ids": None, "trigger": "MANUAL", "actor": "ravi.qa", "actor_role": "QA_ENGINEER"}
            ]
        }
    )

    spec_id: UUID
    test_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=500)
    trigger: RunTrigger = RunTrigger.MANUAL


class ResultResponse(ContractModel):
    id: UUID
    run_id: UUID
    test_case_id: UUID
    tc_code: TestCode
    status: ResultStatus
    expected: ExpectedResult
    observed: dict[str, Any] | None = None
    failed_assertion: Annotated[str, StringConstraints(max_length=300)] | None = None
    latency_ms: int | None = Field(default=None, ge=0)


class RunTotals(ContractModel):
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: int = Field(ge=0)

    @model_validator(mode="after")
    def _totals_add_up(self) -> "RunTotals":
        if self.passed + self.failed + self.errors != self.total:
            raise ValueError("passed + failed + errors must equal total.")
        return self


class RunResponse(ContractModel):
    id: UUID
    spec_id: UUID
    sut_version: str
    trigger: RunTrigger
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    totals: RunTotals
    results: list[ResultResponse]


class DefectHypothesis(ContractModel):
    """An AI-written, clearly labelled hypothesis grounded in failing results."""

    label: Literal["HYPOTHESIS"] = "HYPOTHESIS"
    text: AIText
    cited_result_ids: list[UUID] = Field(min_length=1)
    provider: AIProvider
    model: str | None = None


class DefectResponse(ContractModel):
    id: UUID
    cluster_key: str
    title: str
    rule_key: RuleKey | None = None
    partition: dict[str, ScalarValue]
    status: DefectStatus
    first_run_id: UUID
    evidence_result_ids: list[UUID]
    hypothesis: DefectHypothesis | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Change impact
# ---------------------------------------------------------------------------


class ChangeImpactRequest(ActorFields):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"from_spec_id": "3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01", "actor": "ravi.qa", "actor_role": "QA_ENGINEER"}]
        }
    )

    from_spec_id: UUID


class RuleChange(ContractModel):
    rule_key: RuleKey
    kind: RuleChangeKind
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    changed_fields: list[str] = Field(default_factory=list)


class ImpactedTest(ContractModel):
    test_id: UUID
    tc_code: TestCode
    impact_class: ImpactClass
    reason: Annotated[str, StringConstraints(max_length=300)]
    old_expected: ExpectedResult | None = None
    new_expected: ExpectedResult | None = None
    replacement_test_id: UUID | None = None


class ChangeImpactResponse(ContractModel):
    id: UUID
    from_spec_id: UUID
    to_spec_id: UUID
    rule_changes: list[RuleChange]
    impacted_criteria: list[CriterionCode]
    impacted_tests: list[ImpactedTest]
    counts: dict[ImpactClass, int]
    rerun_test_ids: list[UUID]
    created_at: datetime


# ---------------------------------------------------------------------------
# Audit and metrics
# ---------------------------------------------------------------------------


class AuditEventResponse(ContractModel):
    id: UUID
    ts: datetime
    actor: str
    actor_role: ActorRole
    action: AuditAction
    entity_type: EntityType
    entity_id: UUID
    before_hash: Sha256Hex | None = None
    after_hash: Sha256Hex | None = None
    trace_id: str | None = None
    detail: dict[str, Any] | None = None


class AuditPage(ContractModel):
    items: list[AuditEventResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)


class RunSummary(ContractModel):
    run_id: UUID
    sut_version: str
    finished_at: datetime | None = None
    totals: RunTotals


class MetricsOverviewResponse(ContractModel):
    """Dashboard metrics computed from database rows only.

    Ratios are ``None`` when their denominator is zero, never a made-up value.
    """

    requirements_total: int = Field(ge=0)
    specs_approved: int = Field(ge=0)
    ambiguities_total: int = Field(ge=0)
    ambiguities_resolved: int = Field(ge=0)
    requirement_completeness: float | None = Field(default=None, ge=0, le=1)
    rules_total: int = Field(ge=0)
    rules_with_passing_test: int = Field(ge=0)
    rule_coverage: float | None = Field(default=None, ge=0, le=1)
    tests_by_status: dict[str, int]
    validation_blocks_by_code: dict[str, int]
    last_run: RunSummary | None = None
    open_defects: int = Field(ge=0)
    tests_impacted_pending: int = Field(ge=0)
    ai_calls_total: int = Field(ge=0)
    ai_fallbacks_total: int = Field(ge=0)
    generated_at: datetime


# Models that carry JSON examples; the contract tests validate every example.
MODELS_WITH_EXAMPLES: tuple[type[BaseModel], ...] = (
    ErrorResponse,
    RequirementCreate,
    RequirementVersionCreate,
    RequirementExtraction,
    AnalyzeRequirementRequest,
    ResolveAmbiguityRequest,
    ApproveSpecRequest,
    TestCaseResponse,
    DesignTestsRequest,
    TestReviewRequest,
    RunCreateRequest,
    ChangeImpactRequest,
)
