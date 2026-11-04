"""State machine and role rule tests."""

from __future__ import annotations

import pytest

from app.core import contracts
from app.core.contracts import ActorRole, AmbiguityStatus, SpecStatus
from app.core.errors import ForbiddenError, StateTransitionError
from app.core.state_machine import (
    SPEC_EDITOR_ROLES,
    assert_ambiguity_transition,
    assert_spec_transition,
    assert_test_transition,
    require_role,
)


def test_spec_transitions() -> None:
    assert_spec_transition(SpecStatus.DRAFT, SpecStatus.APPROVED)
    assert_spec_transition(SpecStatus.APPROVED, SpecStatus.SUPERSEDED)
    with pytest.raises(StateTransitionError) as caught:
        assert_spec_transition(SpecStatus.APPROVED, SpecStatus.APPROVED)
    assert caught.value.details["allowed"] == ["SUPERSEDED"]
    with pytest.raises(StateTransitionError):
        assert_spec_transition(SpecStatus.SUPERSEDED, SpecStatus.DRAFT)


def test_ambiguity_transitions() -> None:
    assert_ambiguity_transition(AmbiguityStatus.OPEN, AmbiguityStatus.DEFERRED)
    assert_ambiguity_transition(AmbiguityStatus.DEFERRED, AmbiguityStatus.RESOLVED)
    with pytest.raises(StateTransitionError):
        assert_ambiguity_transition(AmbiguityStatus.RESOLVED, AmbiguityStatus.OPEN)
    with pytest.raises(StateTransitionError):
        assert_ambiguity_transition(AmbiguityStatus.DEFERRED, AmbiguityStatus.DEFERRED)


def test_test_transitions() -> None:
    status = contracts.TestStatus
    assert_test_transition(status.DRAFT, status.APPROVED)
    assert_test_transition(status.APPROVED, status.STALE)
    assert_test_transition(status.STALE, status.APPROVED)
    with pytest.raises(StateTransitionError):
        assert_test_transition(status.BLOCKED, status.APPROVED)
    with pytest.raises(StateTransitionError):
        assert_test_transition(status.REJECTED, status.DRAFT)


def test_roles() -> None:
    require_role(ActorRole.BUSINESS_ANALYST, SPEC_EDITOR_ROLES, "approve")
    with pytest.raises(ForbiddenError) as caught:
        require_role(ActorRole.DEVELOPER, SPEC_EDITOR_ROLES, "approve")
    assert caught.value.details == {"allowed_roles": ["ADMIN", "BUSINESS_ANALYST", "QA_ENGINEER"]}
    assert ActorRole.SYSTEM not in SPEC_EDITOR_ROLES
