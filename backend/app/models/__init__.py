"""SQLAlchemy models for SpecGuard 2.0.

Importing this package registers every table with ``Base.metadata``.
"""

from app.models.audit import AuditEvent, AuditImmutableError, EvalRun, LlmCall, LlmStage
from app.models.execution import ChangeImpact, Defect, Result, Run, SutVersion
from app.models.policy import Policy
from app.models.requirement import Requirement, RequirementVersion
from app.models.specification import AmbiguityRecord, Criterion, Spec, SpecRule
from app.models.test_case import (
    Review,
    TestCase,
    TraceLink,
    TraceLinkType,
    ValidationIssueRecord,
)

__all__ = [
    "AmbiguityRecord",
    "AuditEvent",
    "AuditImmutableError",
    "ChangeImpact",
    "Criterion",
    "Defect",
    "EvalRun",
    "LlmCall",
    "LlmStage",
    "Policy",
    "Requirement",
    "RequirementVersion",
    "Result",
    "Review",
    "Run",
    "Spec",
    "SpecRule",
    "SutVersion",
    "TestCase",
    "TraceLink",
    "TraceLinkType",
    "ValidationIssueRecord",
]
