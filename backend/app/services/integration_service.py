"""Loads the Quality Engine checker delivered by Member 2, if it exists.

Member 2 provides ``app/engine/interface.py`` with::

    def check_spec(
        extraction: RequirementExtraction,
        requirement_text: str,
        policies: Sequence[PolicyResponse],
    ) -> Sequence[ValidationIssue]

Rules for the returned issues:

* Rule-level issues set ``detail={"rule_key": "<RULE_KEY>"}``.
* V02 (ungrounded span) means ``source_span`` is not an exact,
  whitespace-normalised substring of the requirement text or of the rule's
  cited policy text.
* The function is pure Python: no database or HTTP access.

If the module is missing, ``get_spec_checker`` returns ``None``. Rules then stay
``grounded: null`` and approval is blocked until the check can run.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Sequence

from app.core.contracts import PolicyResponse, RequirementExtraction, ValidationIssue

ENGINE_INTERFACE_MODULE = "app.engine.interface"

SpecChecker = Callable[
    [RequirementExtraction, str, Sequence[PolicyResponse]], Sequence[ValidationIssue]
]


def get_spec_checker() -> SpecChecker | None:
    """Return the engine's ``check_spec`` function, or ``None`` if not yet delivered."""
    try:
        module = importlib.import_module(ENGINE_INTERFACE_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name in {"app.engine", ENGINE_INTERFACE_MODULE}:
            return None
        raise
    checker = getattr(module, "check_spec", None)
    return checker if callable(checker) else None
