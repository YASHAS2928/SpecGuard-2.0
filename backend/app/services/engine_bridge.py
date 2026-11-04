"""Bridge between persisted specifications and the Quality Engine."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.contracts import PolicyResponse, RuleType
from app.core.errors import ApiError, IntegrationUnavailableError, NotFoundError
from app.engine.protocol import EngineRule, EngineSpec, QualityEngine
from app.models import RequirementVersion, Spec
from app.services.policy_service import resolve_policy_refs, utc_today

T = TypeVar("T")


def load_spec(db: Session, spec_id: uuid.UUID) -> Spec:
    """Load a specification with its rules and requirement, or raise 404."""
    spec = db.scalars(
        select(Spec).where(Spec.id == spec_id).options(
            selectinload(Spec.rules),
            selectinload(Spec.requirement_version).selectinload(RequirementVersion.requirement),
        )
    ).first()
    if spec is None:
        raise NotFoundError(f"Specification {spec_id} was not found.", details={"spec_id": str(spec_id)})
    return spec


def engine_spec_for(db: Session, spec: Spec, engine: QualityEngine) -> EngineSpec:
    """Return the engine's view of ``spec`` (rule parameters, attached policies, evaluation date)."""
    version = spec.requirement_version
    policies = [PolicyResponse.model_validate(p) for p in resolve_policy_refs(db, version.policy_ids)]
    rules = [
        EngineRule(r.rule_key, RuleType(r.type).value, dict(r.params), r.policy_ref, r.source_span)
        for r in sorted(spec.rules, key=lambda item: item.rule_key)
    ]
    return call_engine(
        lambda: engine.to_engine_spec(
            rules=rules, requirement_code=version.requirement.code,
            requirement_text=version.text, policies=policies, today=utc_today(),
        )
    )


def call_engine(action: Callable[[], T]) -> T:
    """Run an engine call; any engine failure becomes 503 INTEGRATION_UNAVAILABLE."""
    try:
        return action()
    except ApiError:
        raise
    except Exception as exc:
        raise IntegrationUnavailableError(
            f"The Quality Engine failed ({type(exc).__name__})."
        ) from exc
