"""Tests for TurfTruth quote adjustment route, pricing service, and pages."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import store
from main import app
from models import GeminiGardenAnalysisSchema, GeminiTaskEstimate, TaskHourAdjustment
from services.pricing import (
    InvalidHoursError,
    TaskNotFoundError,
    apply_hour_adjustments,
    calculate_line_total_gbp,
    recalculate_quote,
    round_gbp,
    round_hours,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_in_memory_store() -> None:
    """Ensure each test starts with a clean seeded store."""
    store.reset_store()


def test_health_endpoint() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_index_page_renders_quote() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "TurfTruth" in resp.text
    assert "demo-quote-1" in resp.text


def test_get_quote_success_and_not_found() -> None:
    resp = client.get("/quote/demo-quote-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["quote_id"] == "demo-quote-1"
    assert data["total_hours"] == 4.5
    assert data["total_gbp"] == 202.5

    missing = client.get("/quote/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["code"] == "quote_not_found"


def test_post_quote_adjust_happy_path() -> None:
    resp = client.post(
        "/quote/adjust",
        json={
            "quote_id": "demo-quote-1",
            "adjustments": [
                {"task_id": "t1", "hours": 3.0},
                {"task_id": "t3", "hours": 0.5},
            ],
        },
    )
    assert resp.status_code == 200
    quote = resp.json()["quote"]
    by_id = {t["task_id"]: t for t in quote["tasks"]}
    assert by_id["t1"]["estimated_hours"] == 3.0
    assert by_id["t1"]["line_total_gbp"] == 135.0
    assert by_id["t2"]["estimated_hours"] == 1.5
    assert by_id["t2"]["line_total_gbp"] == 67.5
    assert by_id["t3"]["estimated_hours"] == 0.5
    assert by_id["t3"]["line_total_gbp"] == 22.5
    assert quote["total_hours"] == 5.0
    assert quote["total_gbp"] == 225.0

    persisted = client.get("/quote/demo-quote-1").json()
    assert persisted["total_gbp"] == 225.0


@pytest.mark.parametrize("bad_hours", [0, -0.5])
def test_post_quote_adjust_non_positive_hours_rejected(bad_hours: float) -> None:
    resp = client.post(
        "/quote/adjust",
        json={
            "quote_id": "demo-quote-1",
            "adjustments": [{"task_id": "t1", "hours": bad_hours}],
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "validation_error"
    assert "detail" in body


def test_post_quote_adjust_sub_penny_hours_rounding_to_zero_rejected() -> None:
    resp = client.post(
        "/quote/adjust",
        json={
            "quote_id": "demo-quote-1",
            "adjustments": [{"task_id": "t1", "hours": 0.001}],
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "invalid_hours"


def test_post_quote_adjust_unknown_quote_returns_typed_404() -> None:
    resp = client.post(
        "/quote/adjust",
        json={
            "quote_id": "unknown-quote",
            "adjustments": [{"task_id": "t1", "hours": 1.0}],
        },
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "quote_not_found"


def test_post_quote_adjust_unknown_task_returns_typed_404() -> None:
    resp = client.post(
        "/quote/adjust",
        json={
            "quote_id": "demo-quote-1",
            "adjustments": [{"task_id": "no-such-task", "hours": 1.0}],
        },
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "task_not_found"


def test_gbp_rounding_half_up() -> None:
    assert round_gbp(Decimal("12.345")) == 12.35
    assert round_hours(1.335) == 1.34
    assert calculate_line_total_gbp(0.33, 45.55) == 15.03

    resp = client.post(
        "/quote/adjust",
        json={
            "quote_id": "demo-quote-1",
            "adjustments": [{"task_id": "t1", "hours": 1.335}],
        },
    )
    assert resp.status_code == 200
    by_id = {t["task_id"]: t for t in resp.json()["quote"]["tasks"]}
    assert by_id["t1"]["estimated_hours"] == 1.34
    assert by_id["t1"]["line_total_gbp"] == 60.3


def test_pricing_service_errors_and_recalculate() -> None:
    quote = store.get_quote("demo-quote-1")
    assert quote is not None

    recalculated = recalculate_quote(quote)
    assert recalculated.total_gbp == 202.5

    with pytest.raises(TaskNotFoundError):
        apply_hour_adjustments(quote, [TaskHourAdjustment(task_id="bad", hours=1.0)])

    with pytest.raises(InvalidHoursError):
        calculate_line_total_gbp(-1.0, 45.0)

    with pytest.raises(InvalidHoursError):
        round_hours(float("nan"))


def test_post_quote_adjust_disable_and_enable_tasks() -> None:
    payload = {"quote_id": "demo-quote-1", "adjustments": [{"task_id": "t2", "hours": 1.5, "enabled": False}]}
    resp = client.post("/quote/adjust", json=payload)
    assert resp.status_code == 200
    quote = resp.json()["quote"]
    assert {t["task_id"]: t for t in quote["tasks"]}["t2"]["enabled"] is False
    assert (quote["total_hours"], quote["total_gbp"]) == (3.0, 135.0)

    payload["adjustments"][0]["enabled"] = True
    re_enabled = client.post("/quote/adjust", json=payload)
    assert re_enabled.status_code == 200
    assert (re_enabled.json()["quote"]["total_hours"], re_enabled.json()["quote"]["total_gbp"]) == (4.5, 202.5)


def test_gemini_schema_has_no_pricing_fields() -> None:
    forbidden = {"price", "total", "cost", "rate", "gbp", "subtotal"}
    task_fields = set(GeminiTaskEstimate.model_fields.keys())
    schema_fields = set(GeminiGardenAnalysisSchema.model_fields.keys())
    assert not any(any(word in f.lower() for word in forbidden) for f in task_fields)
    assert not any(any(word in f.lower() for word in forbidden) for f in schema_fields)
