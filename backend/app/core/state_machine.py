"""Transition tables and role rules for SpecGuard 2.0.

Services call these helpers before changing a status, so illegal transitions
fail the same way everywhere (HTTP 409 ``STATE_TRANSITION_NOT_ALLOWED``).
Test transitions are used from Milestone 6.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from enum import StrEnum
from typing import TypeVar

from app.core.contracts import ActorRole, AmbiguityStatus, SpecStatus, TestStatus
from app.core.errors import ForbiddenError, StateTransitionError

S = TypeVar("S", bound=StrEnum)

SPEC_TRANSITIONS: Mapping[SpecStatus, frozenset[SpecStatus]] = {
    SpecStatus.DRAFT: frozenset({SpecStatus.APPROVED, SpecStatus.SUPERSEDED}),
    SpecStatus.APPROVED: frozenset({SpecStatus.SUPERSEDED}),
    SpecStatus.SUPERSEDED: frozenset(),
}

AMBIGUITY_TRANSITIONS: Mapping[AmbiguityStatus, frozenset[AmbiguityStatus]] = {
    AmbiguityStatus.OPEN: frozenset({AmbiguityStatus.RESOLVED, AmbiguityStatus.DEFERRED}),
    AmbiguityStatus.DEFERRED: frozenset({AmbiguityStatus.RESOLVED}),
    AmbiguityStatus.RESOLVED: frozenset(),
}

TEST_TRANSITIONS: Mapping[TestStatus, frozenset[TestStatus]] = {
    TestStatus.DRAFT: frozenset(
        {TestStatus.APPROVED, TestStatus.REJECTED, TestStatus.BLOCKED, TestStatus.OBSOLETE}
    ),
    TestStatus.BLOCKED: frozenset({TestStatus.DRAFT, TestStatus.REJECTED, TestStatus.OBSOLETE}),
    TestStatus.APPROVED: frozenset({TestStatus.STALE, TestStatus.OBSOLETE}),
    TestStatus.STALE: frozenset({TestStatus.APPROVED, TestStatus.REJECTED, TestStatus.OBSOLETE}),
    TestStatus.REJECTED: frozenset(),
    TestStatus.OBSOLETE: frozenset(),
}

SPEC_EDITOR_ROLES: frozenset[ActorRole] = frozenset(
    {ActorRole.BUSINESS_ANALYST, ActorRole.QA_ENGINEER, ActorRole.ADMIN}
)


def _assert_transition(
    entity: str, table: Mapping[S, frozenset[S]], current: S, target: S
) -> None:
    allowed = table.get(current, frozenset())
    if target not in allowed:
        raise StateTransitionError(
            f"{entity} cannot move from {current.value} to {target.value}.",
            details={
                "entity": entity,
                "from": current.value,
                "to": target.value,
                "allowed": sorted(state.value for state in allowed),
            },
        )


def assert_spec_transition(current: SpecStatus, target: SpecStatus) -> None:
    """Raise ``StateTransitionError`` unless a specification may move ``current`` -> ``target``."""
    _assert_transition("Specification", SPEC_TRANSITIONS, current, target)


def assert_ambiguity_transition(current: AmbiguityStatus, target: AmbiguityStatus) -> None:
    """Raise ``StateTransitionError`` unless an ambiguity may move ``current`` -> ``target``."""
    _assert_transition("Ambiguity", AMBIGUITY_TRANSITIONS, current, target)


def assert_test_transition(current: TestStatus, target: TestStatus) -> None:
    """Raise ``StateTransitionError`` unless a test may move ``current`` -> ``target``."""
    _assert_transition("Test case", TEST_TRANSITIONS, current, target)


def require_role(actor_role: ActorRole, allowed: Collection[ActorRole], action: str) -> None:
    """Raise ``ForbiddenError`` unless ``actor_role`` is in ``allowed``."""
    if actor_role not in allowed:
        raise ForbiddenError(
            f"Role {actor_role.value} is not allowed to {action}.",
            details={"allowed_roles": sorted(role.value for role in allowed)},
        )
