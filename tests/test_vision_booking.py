"""Tests for TurfTruth vision analysis, calendar retrieval, and slot booking."""

import base64
from pathlib import Path
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

import store
from main import app
from models import GeminiGardenAnalysisSchema, GeminiTaskEstimate
from services.booking import (
    AlreadyBookedError,
    NoSlotAvailableError,
    book_next_free_slot,
)
from services.vision import NoPhotoError, NotAGardenError, analyse_garden_photo

client = TestClient(app)
NOT_A_GARDEN_PATH = Path(__file__).parent / "not_a_garden.png"


@pytest.fixture(autouse=True)
def _reset_in_memory_store() -> None:
    """Ensure each test starts with a clean seeded store."""
    store.reset_store()


def _make_varied_png_b64() -> str:
    """Build a small valid non-uniform PNG encoded as a data URL."""
    width, height = 4, 4
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = b"".join(
        b"\x00" + b"".join(bytes([(x * 45 + y * 15) % 256, 130, 50]) for x in range(width))
        for y in range(height)
    )
    idat = zlib.compress(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def test_vision_sample_garden_and_schema_has_no_gbp_fields() -> None:
    result = analyse_garden_photo(use_sample=True, image_base64=None)
    assert isinstance(result, GeminiGardenAnalysisSchema)
    assert len(result.tasks) == 4
    assert all(t.estimated_hours > 0 and t.visual_evidence for t in result.tasks)

    forbidden = {"price", "total", "cost", "rate", "gbp", "subtotal", "£"}
    for model_cls in (GeminiGardenAnalysisSchema, GeminiTaskEstimate):
        for field_name in model_cls.model_fields:
            assert not any(word in field_name.lower() for word in forbidden)


def test_vision_no_photo_raises() -> None:
    with pytest.raises(NoPhotoError):
        analyse_garden_photo(use_sample=False, image_base64=None)
    with pytest.raises(NoPhotoError):
        analyse_garden_photo(use_sample=False, image_base64="   ")


def test_vision_not_a_garden_png_raises() -> None:
    encoded = base64.b64encode(NOT_A_GARDEN_PATH.read_bytes()).decode("ascii")
    with pytest.raises(NotAGardenError):
        analyse_garden_photo(use_sample=False, image_base64=encoded, filename="not_a_garden.png")
    with pytest.raises(NotAGardenError):
        analyse_garden_photo(use_sample=False, image_base64=encoded, filename="upload.png")


def test_vision_valid_varied_png_succeeds() -> None:
    result = analyse_garden_photo(use_sample=False, image_base64=_make_varied_png_b64())
    assert len(result.tasks) >= 3


def test_post_quote_analyse_sample_and_errors() -> None:
    sample_resp = client.post("/quote/analyse", json={"use_sample": True})
    assert sample_resp.status_code == 200
    quote = sample_resp.json()
    assert quote["quote_id"].startswith("quote-")
    assert len(quote["tasks"]) == 4
    assert quote["total_hours"] == 5.5
    assert quote["total_gbp"] == 247.5
    assert store.get_quote(quote["quote_id"]) is not None

    empty_resp = client.post("/quote/analyse", json={"use_sample": False})
    assert empty_resp.status_code == 400
    assert empty_resp.json()["code"] == "no_photo"

    encoded = base64.b64encode(NOT_A_GARDEN_PATH.read_bytes()).decode("ascii")
    bad_resp = client.post(
        "/quote/analyse",
        json={"use_sample": False, "image_base64": encoded, "filename": "not_a_garden.png"},
    )
    assert bad_resp.status_code == 400
    assert bad_resp.json()["code"] == "not_a_garden"


def test_booking_service_skips_rain_and_avoids_overlap() -> None:
    # Mon 23 Nov is rain; Tue 24 Nov has 09:00-11:30 booked.
    slot_1h = book_next_free_slot("q-short", "Client A", 1.0)
    assert slot_1h.date == "2026-11-24"
    assert (slot_1h.start, slot_1h.end) == ("08:00", "09:00")
    assert slot_1h.is_rain is False

    # 6h does not fit on Tue (5.5h left), skips Wed (rain) and Thu (max 4.5h), lands on Fri.
    slot_6h = book_next_free_slot("q-long", "Client B", 6.0)
    assert slot_6h.date == "2026-11-27"
    assert (slot_6h.start, slot_6h.end) == ("08:00", "14:00")

    with pytest.raises(AlreadyBookedError):
        book_next_free_slot("q-short", "Client A", 1.0)

    with pytest.raises(NoSlotAvailableError):
        book_next_free_slot("q-impossible", "Client C", 12.0)


def test_get_calendar_and_post_booking_next_endpoints() -> None:
    cal_resp = client.get("/calendar")
    assert cal_resp.status_code == 200
    cal = cal_resp.json()
    assert len(cal["days"]) == 5
    assert len(cal["slots"]) == 2

    book_resp = client.post(
        "/booking/next",
        json={"quote_id": "demo-quote-1", "duration_hours": 4.5},
    )
    assert book_resp.status_code == 200
    booked = book_resp.json()["booked_slot"]
    assert booked["date"] == "2026-11-24"
    assert (booked["start"], booked["end"]) == ("11:30", "16:00")
    assert booked["is_rain"] is False

    dup_resp = client.post(
        "/booking/next",
        json={"quote_id": "demo-quote-1", "duration_hours": 1.0},
    )
    assert dup_resp.status_code == 409
    assert dup_resp.json()["code"] == "already_booked"

    missing_resp = client.post(
        "/booking/next",
        json={"quote_id": "no-such-quote", "duration_hours": 1.0},
    )
    assert missing_resp.status_code == 404
    assert missing_resp.json()["code"] == "quote_not_found"

    created = client.post("/quote/analyse", json={"use_sample": True}).json()
    no_slot_resp = client.post(
        "/booking/next",
        json={"quote_id": created["quote_id"], "duration_hours": 12.0},
    )
    assert no_slot_resp.status_code == 400
    assert no_slot_resp.json()["code"] == "no_slot_available"
