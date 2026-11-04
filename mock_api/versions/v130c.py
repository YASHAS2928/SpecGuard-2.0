"""Seeded defect: approved unpaid meal is deducted twice."""

def calculate(start: int, end: int, overnight: bool, meal: int) -> dict[str, int]:
    span = end - start + (1440 if overnight else 0)
    paid = span - 2 * meal
    return {"paid_minutes": paid, "overtime_minutes": max(0, paid - 480)}
