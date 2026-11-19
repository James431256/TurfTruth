"""Unit tests for pure integer-pence pricing functions in pricing.py."""

import math
from decimal import Decimal

import pytest

import pricing
from pricing import (
    HOURLY_RATE_PENCE,
    format_gbp,
    get_hourly_rate_pence,
    line_cost_pence,
    total_pence,
)


def test_default_hourly_rate_pence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default hourly rate is 2500 pence (£25.00/hr) when env is unset or default."""
    monkeypatch.delenv("HOURLY_RATE_PENCE", raising=False)
    assert get_hourly_rate_pence() == 2500
    assert HOURLY_RATE_PENCE == 2500


def test_custom_hourly_rate_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_hourly_rate_pence reads custom integer pence from environment."""
    monkeypatch.setenv("HOURLY_RATE_PENCE", "3250")
    assert get_hourly_rate_pence() == 3250

    monkeypatch.setenv("HOURLY_RATE_PENCE", "-100")
    with pytest.raises(ValueError, match="HOURLY_RATE_PENCE"):
        get_hourly_rate_pence()


@pytest.mark.parametrize(
    ("hours", "rate_pence", "expected_pence"),
    [
        (0.0, 2500, 0),
        (1.0, 2500, 2500),
        (2.5, 2500, 6250),
        (0.25, 2500, 625),
        (0.75, 2500, 1875),
        (4.5, 2500, 11250),
        (1.5, 4500, 6750),
    ],
)
def test_line_cost_pence_standard_hours(
    hours: float,
    rate_pence: int,
    expected_pence: int,
) -> None:
    """Standard hour fractions multiply cleanly into integer pence."""
    assert line_cost_pence(hours, rate_pence) == expected_pence


@pytest.mark.parametrize(
    ("hours", "rate_pence", "expected_pence"),
    [
        # 0.33 * 2500 = 825.0 -> 825
        (0.33, 2500, 825),
        # 0.33 * 4555 = 1503.15 -> 1503
        (0.33, 4555, 1503),
        # 0.5 * 1 = 0.5 -> 1 (half-up rounds .5 up to 1)
        (0.5, 1, 1),
        # 0.25 * 3 = 0.75 -> 1
        (0.25, 3, 1),
        # 0.25 * 1 = 0.25 -> 0
        (0.25, 1, 0),
        # 1.335 * 1000 = 1335.0 -> 1335
        (1.335, 1000, 1335),
        # 0.125 * 100 = 12.5 -> 13 (half-up, not banker's rounding to 12)
        (0.125, 100, 13),
        # 0.375 * 100 = 37.5 -> 38 (half-up)
        (0.375, 100, 38),
    ],
)
def test_line_cost_pence_half_up_rounding(
    hours: float,
    rate_pence: int,
    expected_pence: int,
) -> None:
    """Fractional pence always round half-up (ROUND_HALF_UP) to integer penny."""
    result = line_cost_pence(hours, rate_pence)
    assert isinstance(result, int)
    assert result == expected_pence


@pytest.mark.parametrize(
    "bad_hours",
    [
        -0.01,
        -1.0,
        -100,
        float("nan"),
        float("inf"),
        float("-inf"),
        math.nan,
        True,
        False,
        "2.5",
        None,
        Decimal("-0.5"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_line_cost_pence_rejects_invalid_hours(bad_hours: object) -> None:
    """Negative, NaN, infinite, boolean, or non-numeric hours raise ValueError."""
    with pytest.raises(ValueError):
        line_cost_pence(bad_hours)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_rate", [-1, -2500, True, False, 25.0, "2500", None])
def test_line_cost_pence_rejects_invalid_rate(bad_rate: object) -> None:
    """Negative, boolean, float, or non-int rates raise ValueError."""
    with pytest.raises(ValueError):
        line_cost_pence(1.0, bad_rate)  # type: ignore[arg-type]


def test_total_pence_empty_and_all_unticked() -> None:
    """Empty task list or all unticked tasks return 0 pence."""
    assert total_pence([]) == 0
    assert (
        total_pence(
            [
                {"id": "t1", "hours": 2.0, "enabled": False},
                {"id": "t2", "hours": 1.5, "ticked": False},
            ]
        )
        == 0
    )


def test_total_pence_sums_only_ticked_tasks() -> None:
    """total_pence sums line_cost_pence for enabled/ticked tasks only."""
    tasks = [
        {"id": "t1", "name": "Lawn mow", "hours": 2.0, "enabled": True},
        {"id": "t2", "name": "Hedge trim", "hours": 1.5, "enabled": False},
        {"id": "t3", "name": "Patio weed", "hours": 1.0, "ticked": True},
        {"id": "t4", "name": "Leaf clear", "hours": 0.75, "ticked": False},
        {"id": "t5", "name": "Border edge", "hours": 0.5},  # defaults to enabled=True
    ]
    # Enabled: 2.0 + 1.0 + 0.5 = 3.5h @ 2500p = 8750p
    assert total_pence(tasks, rate_pence=2500) == 8750


def test_total_pence_supports_estimated_hours_key() -> None:
    """total_pence also works with QuoteTask dicts using estimated_hours."""
    tasks = [
        {"task_id": "t1", "estimated_hours": 2.0, "enabled": True},
        {"task_id": "t2", "estimated_hours": 1.5, "enabled": True},
    ]
    assert total_pence(tasks, rate_pence=2500) == 8750


def test_total_pence_rejects_invalid_rate_or_enabled_task_hours() -> None:
    """total_pence propagates ValueError on invalid rate or negative task hours."""
    with pytest.raises(ValueError):
        total_pence([{"hours": -1.0, "enabled": True}])
    with pytest.raises(ValueError):
        total_pence([], rate_pence=-10)


def test_format_gbp() -> None:
    """format_gbp formats integer pence into £XX.XX strings."""
    assert format_gbp(0) == "£0.00"
    assert format_gbp(2500) == "£25.00"
    assert format_gbp(11250) == "£112.50"
    assert isinstance(pricing.HOURLY_RATE_PENCE, int)
