"""Seeded defect: midnight wrap is omitted, then negative span is clamped."""

def calculate(start: int, end: int, overnight: bool, meal: int) -> dict[str, int]:
    span = max(0, end - start) if overnight else end - start
    paid = max(0, span - meal)
    return {"paid_minutes": paid, "overtime_minutes": max(0, paid - 480)}
