"""System under test; deliberately independent from backend.app.engine.oracle."""

import os

from .versions import v130, v130b, v130c, v140, v150

VERSIONS = {"1.3.0": v130, "1.3.0-b": v130b, "1.3.0-c": v130c, "1.4.0": v140, "1.5.0": v150}
DEFAULT_MEAL_MINIMUM = 30


def meal_minimum() -> int:
    """Shortest recorded break that is deducted (``MOCK_MEAL_MIN``, default 30 minutes)."""
    raw = os.getenv("MOCK_MEAL_MIN", "").strip()
    if not raw:
        return DEFAULT_MEAL_MINIMUM
    value = int(raw)
    if value < 0:
        raise ValueError("MOCK_MEAL_MIN must not be negative")
    return value


def calculate(version: str, start: int, end: int, overnight: bool, meal: int | None,
              minimum: int | None = None) -> dict[str, int]:
    """Apply the meal minimum for every version, then the version's own (possibly seeded-bug) logic."""
    threshold = meal_minimum() if minimum is None else minimum
    deducted = meal if meal is not None and meal >= threshold else 0
    return VERSIONS[version].calculate(start, end, overnight, deducted)
