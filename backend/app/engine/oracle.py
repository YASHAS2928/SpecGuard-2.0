"""Independent, synthetic per-shift time-to-pay calculation.

Local HH:MM wall-clock times only. DST and timezone transitions are outside scope.
No mock calculator or AI output is used to derive expected values.
"""

from dataclasses import dataclass
import re

THRESHOLD_MINUTES = 480
MAX_SHIFT_MINUTES = 960


class DomainError(ValueError):
    """Invalid or unsupported demonstration-domain input."""


@dataclass(frozen=True)
class PayResult:
    shift_span_minutes: int
    paid_minutes: int
    overtime_minutes: int


def parse_clock(value: str) -> int:
    if not isinstance(value, str) or re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value) is None:
        raise DomainError("time must be HH:MM in 24-hour local wall-clock format")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def calculate_span(start_time: str, end_time: str, overnight: bool) -> int:
    if type(overnight) is not bool:
        raise DomainError("overnight must be a boolean")
    start, end = parse_clock(start_time), parse_clock(end_time)
    if start == end:
        raise DomainError("equal start and end times are ambiguous")
    if overnight and end > start:
        raise DomainError("overnight indicator requires a midnight crossing")
    if not overnight and end < start:
        raise DomainError("earlier end time requires overnight indicator")
    span = end - start + (1440 if overnight else 0)
    if not 0 < span <= MAX_SHIFT_MINUTES:
        raise DomainError("shift span exceeds the supported 960-minute limit")
    return span


def deduct_meal(span_minutes: int, meal_break_minutes: int) -> int:
    if type(meal_break_minutes) is not int or meal_break_minutes < 0:
        raise DomainError("meal_break_minutes must be a nonnegative integer")
    if meal_break_minutes > span_minutes:
        raise DomainError("meal break cannot exceed shift span")
    return span_minutes - meal_break_minutes


def overtime_minutes(paid_minutes: int, threshold_minutes: int = THRESHOLD_MINUTES) -> int:
    if type(threshold_minutes) is not int or threshold_minutes != THRESHOLD_MINUTES:
        raise DomainError("only the synthetic 480-minute per-shift threshold is supported")
    if type(paid_minutes) is not int or paid_minutes < 0:
        raise DomainError("paid minutes must be nonnegative")
    return max(0, paid_minutes - threshold_minutes)


def calculate(start_time: str, end_time: str, overnight: bool,
              meal_break_minutes: int, threshold_minutes: int = THRESHOLD_MINUTES) -> PayResult:
    span = calculate_span(start_time, end_time, overnight)
    paid = deduct_meal(span, meal_break_minutes)
    return PayResult(span, paid, overtime_minutes(paid, threshold_minutes))
