"""End-to-end browser tests for TurfTruth acceptance criteria C1..C5 and edge cases."""

import re
from pathlib import Path

from tests.e2e.conftest import CDPPage

ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS_DIR = ROOT / "tests" / "screenshots"
NOT_GARDEN_PNG = ROOT / "tests" / "not_a_garden.png"


def _parse_gbp_pence(text: str) -> int:
    match = re.search(r"£\s*([0-9]+(?:\.[0-9]{1,2})?)", text)
    assert match is not None, f"Expected £ amount in {text!r}"
    return round(float(match.group(1)) * 100)


def _analyse_sample_garden(page: CDPPage, base_url: str) -> None:
    page.goto(base_url)
    page.evaluate("window.__navCheck = 'same-page-marker'")
    page.locator('[data-testid="sample-btn"]').click()
    page.locator('[data-testid="analyse-btn"]').click()
    rows = page.locator('[data-testid="task-row"]')
    rows.wait_for(timeout=5.0)
    assert page.evaluate("window.__navCheck") == "same-page-marker"


def test_c1_sample_analysis(page: CDPPage, live_server_url: str) -> None:
    """C1: Sample garden analysis renders >= 3 tasks without reload with hours, £ cost, and evidence."""
    _analyse_sample_garden(page, live_server_url)
    rows = page.locator('[data-testid="task-row"]')
    count = rows.count()
    assert count >= 3
    for idx in range(count):
        row = rows.nth(idx)
        hours_val = float(row.locator('[data-testid="task-hours"]').input_value())
        cost_text = row.locator('[data-testid="task-cost"]').inner_text().strip()
        evidence_text = row.locator('[data-testid="task-evidence"]').inner_text().strip()
        assert hours_val > 0
        assert cost_text.startswith("£") and _parse_gbp_pence(cost_text) > 0
        assert len(evidence_text) > 5

    shot = SCREENSHOTS_DIR / "c1_sample_analysis.png"
    page.screenshot(path=shot)
    assert shot.exists() and shot.stat().st_size > 1000
    assert page.console_errors == []


def test_c2_live_total(page: CDPPage, live_server_url: str) -> None:
    """C2: Adjusting task hours and unticking updates total immediately to ticked hours × rate."""
    _analyse_sample_garden(page, live_server_url)
    rate_pence = _parse_gbp_pence(page.locator('[data-testid="hourly-rate"]').inner_text())
    rows = page.locator('[data-testid="task-row"]')
    initial_total_pence = _parse_gbp_pence(page.locator('[data-testid="total"]').inner_text())

    rows.first.locator('[data-testid="task-hours"]').fill("4.0")
    assert _parse_gbp_pence(page.locator('[data-testid="total"]').inner_text()) != initial_total_pence
    rows.nth(1).locator('[data-testid="task-tick"]').uncheck()

    expected_pence = 0
    for idx in range(rows.count()):
        row = rows.nth(idx)
        is_checked = bool(
            page.evaluate(
                f"document.querySelectorAll('[data-testid=\"task-row\"]')[{idx}]"
                ".querySelector('[data-testid=\"task-tick\"]').checked"
            )
        )
        if is_checked:
            hrs = float(row.locator('[data-testid="task-hours"]').input_value())
            expected_pence += round(hrs * rate_pence)

    updated_total_pence = _parse_gbp_pence(page.locator('[data-testid="total"]').inner_text())
    assert updated_total_pence == expected_pence
    assert updated_total_pence != initial_total_pence

    shot = SCREENSHOTS_DIR / "c2_live_total.png"
    page.screenshot(path=shot)
    assert shot.exists() and shot.stat().st_size > 1000
    assert page.console_errors == []


def test_c3_empty_and_non_garden(page: CDPPage, live_server_url: str) -> None:
    """C3: Empty analyse and non-garden upload show inline error-msg and 0 task rows."""
    page.goto(live_server_url)
    page.locator('[data-testid="analyse-btn"]').click()
    err = page.locator('[data-testid="error-msg"]')
    assert err.is_visible()
    assert len(err.inner_text().strip()) > 0
    assert page.locator('[data-testid="task-row"]').count() == 0

    page.locator('[data-testid="file-input"]').set_input_files(NOT_GARDEN_PNG)
    page.locator('[data-testid="analyse-btn"]').click()
    assert err.is_visible()
    assert "no garden detected" in err.inner_text().strip().lower()
    assert page.locator('[data-testid="task-row"]').count() == 0

    shot = SCREENSHOTS_DIR / "c3_empty_and_non_garden.png"
    page.screenshot(path=shot)
    assert shot.exists() and shot.stat().st_size > 1000
    assert page.console_errors == []


def test_c4_booking_no_clash_no_rain(page: CDPPage, live_server_url: str) -> None:
    """C4: Booking places booked-slot on a dry day without overlapping existing bookings."""
    _analyse_sample_garden(page, live_server_url)
    page.locator('[data-testid="book-btn"]').click()

    booked = page.locator('[data-testid="calendar"] [data-testid="booked-slot"]')
    booked.wait_for(timeout=5.0)
    assert booked.count() == 1
    assert page.locator('[data-testid="rain-day"] [data-testid="booked-slot"]').count() == 0

    slot_meta = page.evaluate(
        """() => {
          const b = document.querySelector('[data-testid="booked-slot"]');
          const sameDayExisting = Array.from(
            document.querySelectorAll(`[data-testid="existing-booking"][data-date="${b.dataset.date}"]`)
          ).map(el => ({start: el.dataset.start, end: el.dataset.end}));
          return {date: b.dataset.date, start: b.dataset.start, end: b.dataset.end, sameDayExisting};
        }"""
    )
    to_min = lambda hhmm: int(hhmm.split(":")[0]) * 60 + int(hhmm.split(":")[1])  # noqa: E731
    b_start, b_end = to_min(slot_meta["start"]), to_min(slot_meta["end"])
    for ex in slot_meta["sameDayExisting"]:
        e_start, e_end = to_min(ex["start"]), to_min(ex["end"])
        assert b_end <= e_start or b_start >= e_end

    shot = SCREENSHOTS_DIR / "c4_booking.png"
    page.screenshot(path=shot)
    assert shot.exists() and shot.stat().st_size > 1000
    assert page.console_errors == []


def test_c5_copy_message(page: CDPPage, live_server_url: str) -> None:
    """C5: Quote message includes tasks, total, and booked date; Copy copies text and shows Copied!."""
    _analyse_sample_garden(page, live_server_url)
    page.locator('[data-testid="book-btn"]').click()
    page.locator('[data-testid="booked-slot"]').wait_for(timeout=5.0)

    first_task = page.locator('[data-testid="task-name"]').first.inner_text().strip()
    total_str = page.locator('[data-testid="total"]').inner_text().strip()
    booked_date = page.evaluate("document.querySelector('[data-testid=\"booked-slot\"]').dataset.date")
    quote_msg = page.locator('[data-testid="quote-msg"]').inner_text().strip()

    assert first_task in quote_msg or "Overgrown lawn" in quote_msg
    assert total_str in quote_msg
    assert booked_date in quote_msg

    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    copy_btn = page.locator('[data-testid="copy-btn"]')
    copy_btn.click()
    assert copy_btn.inner_text().strip() == "Copied!"
    clip_text = page.evaluate("navigator.clipboard.readText()")
    assert clip_text.strip() == quote_msg

    shot = SCREENSHOTS_DIR / "c5_copy_message.png"
    page.screenshot(path=shot)
    assert shot.exists() and shot.stat().st_size > 1000
    assert page.console_errors == []


def test_edge_cases_hours_double_book_and_mobile_viewport(
    page: CDPPage,
    live_server_url: str,
) -> None:
    """Edge cases: invalid hours never yield NaN/negative total, double-click books once, 375px layout."""
    _analyse_sample_garden(page, live_server_url)
    hours_input = page.locator('[data-testid="task-hours"]').first
    total_loc = page.locator('[data-testid="total"]')

    for invalid_val in ("-5", "999", "abc"):
        hours_input.fill(invalid_val)
        total_txt = total_loc.inner_text().strip()
        assert "NaN" not in total_txt and "-" not in total_txt
        assert _parse_gbp_pence(total_txt) >= 0

    hours_input.fill("2.0")
    page.locator('[data-testid="book-btn"]').dblclick()
    page.locator('[data-testid="booked-slot"]').wait_for(timeout=5.0)
    assert page.locator('[data-testid="booked-slot"]').count() == 1

    page.set_viewport_size({"width": 375, "height": 812})
    page.wait_for_idle(0.1)
    scroll_width = int(page.evaluate("document.documentElement.scrollWidth"))
    assert scroll_width <= 375
    assert page.console_errors == []
