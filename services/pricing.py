"""Pure-Python £ pricing and hour-adjustment calculations."""

import math
from decimal import Decimal, ROUND_HALF_UP

from models import Quote, QuoteTask, TaskHourAdjustment

DEFAULT_HOURLY_RATE_GBP = 45.0
_PENNY = Decimal("0.01")


class QuotePricingError(Exception):
    """Base error for quote pricing and adjustment failures."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class TaskNotFoundError(QuotePricingError):
    """Raised when an adjustment references a task_id not in the quote."""

    def __init__(self, task_id: str) -> None:
        super().__init__(f"Task '{task_id}' not found in quote.", code="task_not_found")


class InvalidHoursError(QuotePricingError):
    """Raised when adjusted hours are <= 0 or non-finite."""

    def __init__(self, hours: float) -> None:
        super().__init__(
            f"Invalid hours value: {hours}. Must be a finite number > 0.",
            code="invalid_hours",
        )


def round_gbp(amount: Decimal) -> float:
    """Round a Decimal GBP amount to 2 decimal places using half-up."""
    return float(amount.quantize(_PENNY, rounding=ROUND_HALF_UP))


def round_hours(hours: float) -> float:
    """Round hours to 2 decimal places using half-up."""
    if not math.isfinite(hours) or hours <= 0:
        raise InvalidHoursError(hours)
    rounded = float(Decimal(str(hours)).quantize(_PENNY, rounding=ROUND_HALF_UP))
    if rounded <= 0:
        raise InvalidHoursError(hours)
    return rounded


def calculate_line_total_gbp(hours: float, hourly_rate_gbp: float) -> float:
    """Compute line total in £ from hours and hourly rate."""
    if not math.isfinite(hours) or hours <= 0:
        raise InvalidHoursError(hours)
    total = Decimal(str(hours)) * Decimal(str(hourly_rate_gbp))
    return round_gbp(total)


def recalculate_quote(quote: Quote) -> Quote:
    """Recalculate each task line total and quote-wide hours/£ totals."""
    updated_tasks: list[QuoteTask] = []
    total_hours = Decimal("0.00")
    total_gbp = Decimal("0.00")

    for task in quote.tasks:
        clean_hours = round_hours(task.estimated_hours)
        line_total = calculate_line_total_gbp(clean_hours, task.hourly_rate_gbp)
        updated_tasks.append(
            task.model_copy(
                update={
                    "estimated_hours": clean_hours,
                    "line_total_gbp": line_total,
                }
            )
        )
        if task.enabled:
            total_hours += Decimal(str(clean_hours))
            total_gbp += Decimal(str(line_total))

    return quote.model_copy(
        update={
            "tasks": updated_tasks,
            "total_hours": round_gbp(total_hours),
            "total_gbp": round_gbp(total_gbp),
        }
    )


def apply_hour_adjustments(
    quote: Quote,
    adjustments: list[TaskHourAdjustment],
) -> Quote:
    """Apply gardener hour and enabled adjustments to a quote and recalculate £ totals."""
    tasks_by_id = {task.task_id: task for task in quote.tasks}
    updates: dict[str, tuple[float, bool]] = {}

    for adj in adjustments:
        if adj.task_id not in tasks_by_id:
            raise TaskNotFoundError(adj.task_id)
        updates[adj.task_id] = (round_hours(adj.hours), adj.enabled)

    new_tasks = [
        task.model_copy(
            update={
                "estimated_hours": updates[task.task_id][0],
                "enabled": updates[task.task_id][1],
            }
        )
        if task.task_id in updates
        else task
        for task in quote.tasks
    ]
    return recalculate_quote(quote.model_copy(update={"tasks": new_tasks}))
