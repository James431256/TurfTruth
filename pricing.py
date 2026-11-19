"""Pure integer-pence pricing functions for TurfTruth."""

import math
import os
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

_DEFAULT_RATE_STR = "2500"
_ONE_PENNY = Decimal("1")


def get_hourly_rate_pence() -> int:
    """Read HOURLY_RATE_PENCE from the environment (default 2500 = £25.00/hr)."""
    raw = os.environ.get("HOURLY_RATE_PENCE", _DEFAULT_RATE_STR).strip()
    if not raw:
        return int(_DEFAULT_RATE_STR)
    rate = int(raw)
    if rate < 0:
        raise ValueError("HOURLY_RATE_PENCE must be >= 0")
    return rate


HOURLY_RATE_PENCE: int = get_hourly_rate_pence()


def _validate_rate(rate_pence: int) -> int:
    if isinstance(rate_pence, bool) or not isinstance(rate_pence, int) or rate_pence < 0:
        raise ValueError(f"Invalid rate_pence: {rate_pence!r}. Must be an integer >= 0.")
    return rate_pence


def _validate_hours(hours: float | int | Decimal) -> Decimal:
    if isinstance(hours, bool) or not isinstance(hours, (int, float, Decimal)):
        raise ValueError(f"Invalid hours: {hours!r}. Must be a finite number >= 0.")
    if isinstance(hours, float) and not math.isfinite(hours):
        raise ValueError(f"Invalid hours: {hours!r}. Must be a finite number >= 0.")
    try:
        dec_hours = Decimal(str(hours))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid hours: {hours!r}.") from exc
    if not dec_hours.is_finite() or dec_hours < 0:
        raise ValueError(f"Invalid hours: {hours!r}. Must be a finite number >= 0.")
    return dec_hours


def line_cost_pence(hours: float, rate_pence: int = HOURLY_RATE_PENCE) -> int:
    """Calculate a single task's cost in integer pence, rounded half-up."""
    dec_hours = _validate_hours(hours)
    clean_rate = _validate_rate(rate_pence)
    exact_pence = dec_hours * Decimal(clean_rate)
    rounded = exact_pence.quantize(_ONE_PENNY, rounding=ROUND_HALF_UP)
    return int(rounded)


def total_pence(
    tasks: Iterable[Mapping[str, Any]],
    rate_pence: int = HOURLY_RATE_PENCE,
) -> int:
    """Calculate the total quote cost in integer pence for all ticked/enabled tasks."""
    clean_rate = _validate_rate(rate_pence)
    total = 0
    for task in tasks:
        if "enabled" in task:
            is_enabled = bool(task["enabled"])
        elif "ticked" in task:
            is_enabled = bool(task["ticked"])
        else:
            is_enabled = True
        if not is_enabled:
            continue
        hours = task["hours"] if "hours" in task else task["estimated_hours"]
        total += line_cost_pence(hours, clean_rate)
    return total


def format_gbp(pence: int) -> str:
    """Format an integer pence value as £XX.XX."""
    clean_pence = _validate_rate(pence)
    pounds = (Decimal(clean_pence) / Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return f"£{pounds:.2f}"
