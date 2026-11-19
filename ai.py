"""AI pipeline for garden photo analysis, DEMO_MODE fixtures, and server-side sanitisation."""

import hashlib
import json
import logging
import math
import os
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from services.vision import _is_uniform_png, is_valid_image_bytes

try:
    from google import genai as _genai  # type: ignore[import-not-found]
except ImportError:
    _genai = None

genai: Any = _genai
logger = logging.getLogger("turftruth.ai")

PROMPT_VERSION: str = "analyse_v1"
PROMPT_PATH: Path = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.txt"
FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"
NOT_GARDEN_MSG: str = "No garden detected in this photo - nothing to quote."
SAMPLE_GARDEN_SHA256 = "450ebc3e8c4bb35aa2077960af714de30c92165975cc0863ba7661d27a0ee5da"
NOT_A_GARDEN_SHA256 = "5e1800bc338bdea9bf399c629abffea3d34badfca8381c61113a2501a2789e8c"
FIXTURE_BY_SHA256: dict[str, str] = {
    SAMPLE_GARDEN_SHA256: "sample_garden.json",
    NOT_A_GARDEN_SHA256: "not_a_garden.json",
}
_NON_GARDEN_TOKENS = ("not_a_garden", "not-a-garden", "non_garden", "non-garden", "no_garden", "blank", "indoor")


class AIError(Exception):
    code: str = "ai_error"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class AITimeoutError(AIError):
    code = "ai_timeout"


class AIUpstreamError(AIError):
    code = "ai_error"


class AISchemaError(AIError):
    code = "schema_failure"


class InvalidImageError(AIError):
    code = "invalid_image"


class RawTaskEstimate(BaseModel):
    name: str
    hours: float
    evidence: str


class RawGardenAnalysis(BaseModel):
    is_garden: bool
    tasks: list[RawTaskEstimate]


class SanitisedTask(BaseModel):
    id: str
    name: str
    hours: float
    evidence: str

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class AnalysisResult(BaseModel):
    is_garden: bool
    message: str | None = None
    tasks: list[SanitisedTask]
    prompt_version: str = PROMPT_VERSION
    mode: Literal["live", "demo"]

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class AttrDict(dict[str, Any]):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def model_dump(self) -> dict[str, Any]:
        return dict(self)


def get_mode() -> Literal["live", "demo"]:
    if os.environ.get("DEMO_MODE", "").strip().lower() in ("1", "true", "yes"):
        return "demo"
    return "live" if os.environ.get("GEMINI_API_KEY", "").strip() else "demo"


def _round_quarter_hour(hours: float) -> float:
    clamped = min(40.0, max(0.25, float(hours)))
    quarters = (Decimal(str(clamped)) * Decimal("4")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(min(Decimal("40.0"), max(Decimal("0.25"), quarters / Decimal("4"))))


def sanitise_analysis(
    raw: RawGardenAnalysis | dict[str, Any],
    mode: Literal["live", "demo"] = "demo",
) -> AnalysisResult:
    try:
        parsed = raw if isinstance(raw, RawGardenAnalysis) else RawGardenAnalysis.model_validate(raw)
    except ValidationError as exc:
        raise AISchemaError("Analysis output failed schema validation.") from exc
    if not parsed.is_garden:
        return AnalysisResult(is_garden=False, message=NOT_GARDEN_MSG, tasks=[], prompt_version=PROMPT_VERSION, mode=mode)
    kept: list[SanitisedTask] = []
    for item in parsed.tasks:
        name, evidence = item.name.strip(), item.evidence.strip()
        if not name or not evidence or isinstance(item.hours, bool) or math.isnan(item.hours):
            continue
        hours_val = 40.0 if item.hours == float("inf") else (0.25 if item.hours == float("-inf") else item.hours)
        kept.append(SanitisedTask(id=f"t{len(kept) + 1}", name=name, hours=_round_quarter_hour(hours_val), evidence=evidence))
        if len(kept) >= 12:
            break
    return AnalysisResult(is_garden=True, message=None, tasks=kept, prompt_version=PROMPT_VERSION, mode=mode)


def _gemini_config(response_schema: type[BaseModel] = RawGardenAnalysis) -> dict[str, Any]:
    return {"response_mime_type": "application/json", "response_schema": response_schema, "http_options": {"timeout": 15000}}


def call_gemini(image_bytes: bytes, mime_type: str = "image/png") -> dict[str, Any] | RawGardenAnalysis:
    if genai is None:
        raise AIUpstreamError("google-genai SDK is not available.")
    prompt_text = PROMPT_PATH.read_text(encoding="utf-8") if PROMPT_PATH.exists() else "Analyse garden."
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", "").strip())
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt_text, {"mime_type": mime_type, "data": image_bytes}],
        config=_gemini_config(response_schema=RawGardenAnalysis),
    )
    return resp.parsed if getattr(resp, "parsed", None) is not None else json.loads(resp.text)


_call_gemini = call_gemini


def analyse_image(image_bytes: bytes, mime_type: str = "image/png", filename: str | None = None) -> AttrDict:
    if not image_bytes or not is_valid_image_bytes(image_bytes):
        raise InvalidImageError("Uploaded file is not a valid image.")
    mode = get_mode()
    logger.info("Running garden analysis mode=%s prompt_version=%s", mode, PROMPT_VERSION)
    if mode == "demo":
        digest, fname = hashlib.sha256(image_bytes).hexdigest(), (filename or "").lower()
        non_garden = (
            FIXTURE_BY_SHA256.get(digest) == "not_a_garden.json"
            or any(tok in fname for tok in _NON_GARDEN_TOKENS)
            or b"not_a_garden" in image_bytes
            or _is_uniform_png(image_bytes)
        )
        fixture_file = "not_a_garden.json" if non_garden else FIXTURE_BY_SHA256.get(digest, "sample_garden.json")
        raw_payload = json.loads((FIXTURES_DIR / fixture_file).read_text(encoding="utf-8"))
        result = sanitise_analysis(RawGardenAnalysis.model_validate(raw_payload), mode="demo")
    else:
        try:
            caller = _call_gemini if _call_gemini is not call_gemini else call_gemini
            raw_out = caller(image_bytes, mime_type)
            validated = raw_out if isinstance(raw_out, RawGardenAnalysis) else RawGardenAnalysis.model_validate(raw_out)
            result = sanitise_analysis(validated, mode="live")
        except AIError:
            raise
        except (ValidationError, json.JSONDecodeError) as exc:
            raise AISchemaError("Gemini output did not match RawGardenAnalysis schema.") from exc
        except TimeoutError as exc:
            raise AITimeoutError("Gemini request timed out after 15 seconds.") from exc
        except Exception as exc:
            if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
                raise AITimeoutError("Gemini request timed out after 15 seconds.") from exc
            raise AIUpstreamError("Gemini upstream request failed.") from exc
    dumped = result.model_dump()
    dumped["tasks"] = [AttrDict(t) for t in dumped["tasks"]]
    return AttrDict(dumped)
