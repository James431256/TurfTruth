"""FastAPI TestClient integration tests for /api/* and /health endpoints."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import ai
import main
import store

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PNG = ROOT / "static" / "sample_garden.png"
NOT_GARDEN_PNG = ROOT / "tests" / "not_a_garden.png"
FORBIDDEN_PRICE_KEYS = {"price", "cost", "rate", "total", "gbp", "pence", "amount"}


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure clean store and DEMO_MODE=1 before each test."""
    monkeypatch.setenv("DEMO_MODE", "1")
    store.reset_store()


@pytest.fixture()
def client() -> TestClient:
    """Return a FastAPI TestClient bound to main.app."""
    return TestClient(main.app)


def _to_minutes(hhmm: str) -> int:
    hours, mins = hhmm.split(":")
    return int(hours) * 60 + int(mins)


def _assert_error_envelope(resp: Any, expected_status: int) -> dict[str, Any]:
    assert resp.status_code == expected_status
    body = resp.json()
    assert "error" in body
    assert isinstance(body["error"].get("code"), str) and body["error"]["code"]
    assert isinstance(body["error"].get("message"), str) and body["error"]["message"]
    return body


def test_analyse_sample_image_returns_tasks_without_price_fields(client: TestClient) -> None:
    """Sample image upload returns >= 3 tasks and zero pricing fields in schema or output."""
    img_bytes = SAMPLE_PNG.read_bytes()
    resp = client.post(
        "/api/analyse",
        files={"image": ("sample_garden.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_garden"] is True
    assert data["message"] is None
    assert data["prompt_version"] == ai.PROMPT_VERSION
    assert len(data["tasks"]) >= 3
    for task in data["tasks"]:
        assert set(task.keys()) == {"id", "name", "hours", "evidence"}
        assert not (FORBIDDEN_PRICE_KEYS & set(task.keys()))
        assert task["hours"] >= 0.25
        assert task["name"].strip() and task["evidence"].strip()

    raw_task_props = set(ai.RawTaskEstimate.model_json_schema().get("properties", {}).keys())
    raw_root_props = set(ai.RawGardenAnalysis.model_json_schema().get("properties", {}).keys())
    assert not (FORBIDDEN_PRICE_KEYS & raw_task_props)
    assert not (FORBIDDEN_PRICE_KEYS & raw_root_props)


def test_analyse_no_file_returns_400(client: TestClient) -> None:
    """POST /api/analyse without an uploaded file returns 400 with error envelope."""
    resp = client.post("/api/analyse")
    body = _assert_error_envelope(resp, 400)
    assert body["error"]["code"] in ("no_file", "no_photo", "invalid_image")


def test_analyse_non_image_bytes_returns_400(client: TestClient) -> None:
    """POST /api/analyse with non-image payload returns 400 invalid_image."""
    resp = client.post(
        "/api/analyse",
        files={"image": ("notes.txt", b"Plain text is not a valid image", "text/plain")},
    )
    body = _assert_error_envelope(resp, 400)
    assert body["error"]["code"] == "invalid_image"


def test_analyse_over_10mb_returns_400(client: TestClient) -> None:
    """POST /api/analyse with >10MB file returns 400 file_too_large."""
    oversized = b"\x89PNG\r\n\x1a\n" + (b"\x00" * (10 * 1024 * 1024 + 128))
    resp = client.post(
        "/api/analyse",
        files={"image": ("huge_garden.png", oversized, "image/png")},
    )
    body = _assert_error_envelope(resp, 400)
    assert body["error"]["code"] == "file_too_large"


def test_analyse_not_a_garden_returns_empty_tasks(client: TestClient) -> None:
    """Not-a-garden image returns is_garden=false, empty tasks, and helpful message."""
    img_bytes = NOT_GARDEN_PNG.read_bytes()
    resp = client.post(
        "/api/analyse",
        files={"image": ("not_a_garden.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_garden"] is False
    assert data["tasks"] == []
    assert data["message"] == "No garden detected in this photo - nothing to quote."


def test_analyse_gemini_timeout_returns_504(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mocked Gemini timeout in live mode returns 504 with {error: {code, message}}."""
    monkeypatch.setenv("DEMO_MODE", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-live-key")

    def _raise_timeout(*_args: Any, **_kwargs: Any) -> Any:
        raise TimeoutError("Gemini request timed out")

    monkeypatch.setattr(ai, "call_gemini", _raise_timeout)
    monkeypatch.setattr(ai, "_call_gemini", _raise_timeout)
    resp = client.post(
        "/api/analyse",
        files={"image": ("sample_garden.png", SAMPLE_PNG.read_bytes(), "image/png")},
    )
    body = _assert_error_envelope(resp, 504)
    assert body["error"]["code"] == "ai_timeout"


def test_calendar_and_book_no_overlap_and_no_rain(client: TestClient) -> None:
    """Booking chooses the earliest dry gap and never overlaps existing or rain slots."""
    cal_before = client.get("/api/calendar")
    assert cal_before.status_code == 200
    cal_data = cal_before.json()
    week_before = {d["date"]: d for d in cal_data["week"]}
    work_start = _to_minutes(cal_data["working_hours"]["start"])
    work_end = _to_minutes(cal_data["working_hours"]["end"])

    book_resp = client.post("/api/book", json={"hours": 4.5})
    assert book_resp.status_code == 200
    booked = book_resp.json()
    slot = booked["slot"]
    assert slot is not None
    assert booked["message"]

    day_info = week_before[slot["date"]]
    assert day_info["rain"] is False
    s_start, s_end = _to_minutes(slot["start"]), _to_minutes(slot["end"])
    assert work_start <= s_start < s_end <= work_end
    for existing in day_info["bookings"]:
        e_start, e_end = _to_minutes(existing["start"]), _to_minutes(existing["end"])
        assert s_end <= e_start or s_start >= e_end


@pytest.mark.parametrize("bad_hours", [0, -1.5, 45.0, "not-a-number"])
def test_book_invalid_hours_returns_400(client: TestClient, bad_hours: Any) -> None:
    """POST /api/book with non-positive, huge, or invalid hours returns 400."""
    resp = client.post("/api/book", json={"hours": bad_hours})
    _assert_error_envelope(resp, 400)


def test_health_endpoint(client: TestClient) -> None:
    """GET /health returns 200 with status, mode, and prompt_version."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["mode"] == "demo"
    assert data["prompt_version"] == ai.PROMPT_VERSION
