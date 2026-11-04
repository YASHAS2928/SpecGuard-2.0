"""Spec-level checks that connect the Quality Engine to the backend's analysis step.

The backend calls ``check_spec`` right after the AI extracts a specification
(``app.services.spec_service``). Contract, all of it enforced by the backend:

* Return ``ValidationIssue`` records (never dicts). Any exception or any other
  item type makes the API answer 503 ``INTEGRATION_UNAVAILABLE`` and roll back.
* Pure Python: no database, HTTP or environment access.
* V02 issues must carry ``detail={"rule_key": <a rule of this extraction>}``.
  The backend marks exactly those rules ``grounded=False`` and every other rule
  ``grounded=True``.
* Every BLOCK issue returned stops approval, so only checks that should block
  are returned here. V13 (unresolved parameter) is owned by the backend and the
  test-case checks V05-V12 belong to ``validator.validate_cases``.

Checks:

* V02 - ``source_span`` is not an exact (case-sensitive), whitespace-normalised
  substring of the requirement text or of the rule's *cited* policy text.
  Rules without a ``policy_ref`` are checked against the requirement text only.
* V03 - a rule cites a policy that is not attached to the requirement version.
  The rule is also reported as V02 because its policy source cannot be verified.
* V04 - an attached policy has expired (``effective_to`` before today, UTC).
  Policies that are not effective *yet* are allowed: teams build and test for
  announced changes. Dates are inclusive.

The test-case validator keeps its stricter V04 (not yet effective or expired):
it takes the evaluation date from its caller through ``on_date``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, datetime, timezone

from app.core.contracts import (
    IssueSeverity,
    PolicyResponse,
    RequirementExtraction,
    ValidationCode,
    ValidationIssue,
)

from .grounding import grounded

REQUIREMENT_SOURCE = "requirement"


def locate_span(span: str, text: str) -> tuple[int, int] | None:
    """Return the character offsets of ``span`` in ``text``, ignoring whitespace differences."""
    tokens = span.split()
    if not tokens:
        return None
    match = re.search(r"\s+".join(re.escape(token) for token in tokens), text)
    return (match.start(), match.end()) if match else None


def _span_is_grounded(span: str, source_id: str, sources: dict[str, str]) -> bool:
    location = locate_span(span, sources[source_id])
    if location is None:
        return False
    start, end = location
    claim = {"source_id": source_id, "start": start, "end": end, "text": sources[source_id][start:end]}
    return grounded(claim, sources)


def check_spec(
    extraction: RequirementExtraction,
    requirement_text: str,
    policies: Sequence[PolicyResponse],
    *,
    today: date | None = None,
) -> list[ValidationIssue]:
    """Return the blocking spec-level issues found in ``extraction`` (empty when clean).

    ``today`` exists for tests; the backend never passes it.
    """
    day = today or datetime.now(timezone.utc).date()
    by_ref = {policy.ref: policy for policy in policies}
    sources = {REQUIREMENT_SOURCE: requirement_text}
    sources.update({ref: policy.rule_text for ref, policy in by_ref.items()})
    issues: list[ValidationIssue] = []

    for rule in extraction.rules:
        unknown_policy = rule.policy_ref is not None and rule.policy_ref not in by_ref
        if unknown_policy:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.V03_POLICY_UNKNOWN,
                    severity=IssueSeverity.BLOCK,
                    message=f"{rule.rule_key} cites {rule.policy_ref}, which is not attached to this requirement version.",
                    field_path=f"rules.{rule.rule_key}.policy_ref",
                    detail={"rule_key": rule.rule_key, "policy_ref": rule.policy_ref},
                )
            )
        candidates = [REQUIREMENT_SOURCE]
        if rule.policy_ref is not None and not unknown_policy:
            candidates.append(rule.policy_ref)
        if unknown_policy or not any(
            _span_is_grounded(rule.source_span, source_id, sources) for source_id in candidates
        ):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.V02_UNGROUNDED_SPAN,
                    severity=IssueSeverity.BLOCK,
                    message=f"The source text of {rule.rule_key} was not found in the requirement or its cited policy.",
                    field_path=f"rules.{rule.rule_key}.source_span",
                    detail={"rule_key": rule.rule_key, "policy_ref": rule.policy_ref},
                )
            )

    for policy in policies:
        if policy.effective_to is None or policy.effective_to >= day:
            continue
        message = f"{policy.ref} expired on {policy.effective_to.isoformat()}."
        citing = [rule for rule in extraction.rules if rule.policy_ref == policy.ref]
        if not citing:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.V04_POLICY_NOT_EFFECTIVE,
                    severity=IssueSeverity.BLOCK,
                    message=message,
                    detail={"policy_ref": policy.ref, "effective_to": policy.effective_to.isoformat()},
                )
            )
        for rule in citing:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.V04_POLICY_NOT_EFFECTIVE,
                    severity=IssueSeverity.BLOCK,
                    message=message,
                    field_path=f"rules.{rule.rule_key}.policy_ref",
                    detail={
                        "rule_key": rule.rule_key,
                        "policy_ref": policy.ref,
                        "effective_to": policy.effective_to.isoformat(),
                    },
                )
            )
    return issues
