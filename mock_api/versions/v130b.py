"""Seeded defect: overtime starts at paid minute 480 instead of 481."""

def calculate(start: int, end: int, overnight: bool, meal: int) -> dict[str, int]:
    span = end - start + (1440 if overnight else 0)
    paid = span - meal
    return {"paid_minutes": paid, "overtime_minutes": max(0, paid - 479)}
