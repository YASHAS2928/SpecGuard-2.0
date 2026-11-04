"""System under test; deliberately independent from backend.app.engine.oracle."""

from .versions import v130, v130b, v130c, v140

VERSIONS = {"1.3.0": v130, "1.3.0-b": v130b, "1.3.0-c": v130c, "1.4.0": v140}


def calculate(version: str, start: int, end: int, overnight: bool, meal: int) -> dict[str, int]:
    return VERSIONS[version].calculate(start, end, overnight, meal)
