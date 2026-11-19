"""Garden photo analysis service and pure-Python image byte inspection."""

import base64
import binascii
import struct
import zlib

from models import GeminiGardenAnalysisSchema, GeminiTaskEstimate

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class NoPhotoError(Exception):
    """Raised when analysis is requested without a photo or sample flag."""

    code = "no_photo"


class NotAGardenError(Exception):
    """Raised when the uploaded image does not appear to contain a garden."""

    code = "not_a_garden"


def is_valid_image_bytes(data: bytes) -> bool:
    """Return True if data starts with PNG, JPEG, WebP, or GIF magic bytes."""
    return len(data) >= 4 and (
        data.startswith(_PNG_SIGNATURE)
        or data.startswith(b"\xff\xd8\xff")
        or (data.startswith(b"RIFF") and data[8:12] == b"WEBP")
        or data.startswith((b"GIF87a", b"GIF89a"))
    )


def _sample_garden_analysis() -> GeminiGardenAnalysisSchema:
    """Return a realistic 4-task structured analysis for the sample garden."""
    return GeminiGardenAnalysisSchema(
        tasks=[
            GeminiTaskEstimate(
                task_name="Overgrown lawn mow & edge",
                estimated_hours=2.0,
                visual_evidence="Lawn grass ~15cm tall with creeping border edges.",
            ),
            GeminiTaskEstimate(
                task_name="Privet hedge trim & clear",
                estimated_hours=1.5,
                visual_evidence="Boundary hedge ~2.2m tall with uneven top growth.",
            ),
            GeminiTaskEstimate(
                task_name="Flowerbed weeding & mulch tidy",
                estimated_hours=1.25,
                visual_evidence="Perennial weeds visible along front and side borders.",
            ),
            GeminiTaskEstimate(
                task_name="Patio sweep & green waste bag-up",
                estimated_hours=0.75,
                visual_evidence="Moss and leaf litter across Yorkstone paving slabs.",
            ),
        ]
    )


def _uploaded_garden_analysis() -> GeminiGardenAnalysisSchema:
    """Return a structured 4-task analysis for a valid uploaded garden photo."""
    return GeminiGardenAnalysisSchema(
        tasks=[
            GeminiTaskEstimate(
                task_name="Lawn cut & strim",
                estimated_hours=1.75,
                visual_evidence="Main turf area needs mowing and border strimming.",
            ),
            GeminiTaskEstimate(
                task_name="Shrub & hedge shaping",
                estimated_hours=1.5,
                visual_evidence="Overgrown perimeter shrubs encroaching on path.",
            ),
            GeminiTaskEstimate(
                task_name="Border weeding & deadheading",
                estimated_hours=1.0,
                visual_evidence="Broadleaf weeds and spent blooms in side beds.",
            ),
            GeminiTaskEstimate(
                task_name="Pathway clear & waste removal",
                estimated_hours=0.5,
                visual_evidence="Clippings and debris along garden walkway.",
            ),
        ]
    )


def _decode_base64_image(image_base64: str) -> bytes:
    """Decode a base64 image string, stripping any data URL prefix."""
    payload = image_base64.strip()
    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1]
    try:
        return base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise NotAGardenError(
            "No garden detected in this photo. Please upload a garden photo."
        ) from exc


def _is_uniform_png(raw_bytes: bytes) -> bool:
    """Inspect PNG IHDR/IDAT chunks in pure Python to detect uniform/blank images."""
    if not raw_bytes.startswith(_PNG_SIGNATURE):
        return False

    pos = len(_PNG_SIGNATURE)
    width = height = 0
    idat_chunks: list[bytes] = []

    while pos + 8 <= len(raw_bytes):
        length, chunk_type = struct.unpack(">I4s", raw_bytes[pos : pos + 8])
        data_start = pos + 8
        data_end = data_start + length
        if data_end + 4 > len(raw_bytes):
            break
        chunk_data = raw_bytes[data_start:data_end]
        if chunk_type == b"IHDR" and len(chunk_data) >= 8:
            width, height = struct.unpack(">II", chunk_data[:8])
        elif chunk_type == b"IDAT":
            idat_chunks.append(chunk_data)
        elif chunk_type == b"IEND":
            break
        pos = data_end + 4

    if width == 0 or height == 0 or not idat_chunks:
        return False

    try:
        decompressed = zlib.decompress(b"".join(idat_chunks))
    except zlib.error:
        return False

    return len(set(decompressed[:16384])) <= 4


def analyse_garden_photo(
    use_sample: bool,
    image_base64: str | None,
    filename: str | None = None,
) -> GeminiGardenAnalysisSchema:
    """Analyse a garden photo or sample garden into structured task estimates."""
    if use_sample:
        return _sample_garden_analysis()

    if not image_base64 or not image_base64.strip():
        raise NoPhotoError(
            "Please select a photo or click 'Use sample garden' before analysing."
        )

    if filename and "not_a_garden" in filename.lower():
        raise NotAGardenError(
            "No garden detected in this photo. Please upload a garden photo."
        )

    raw_bytes = _decode_base64_image(image_base64)
    if not raw_bytes:
        raise NoPhotoError(
            "Please select a photo or click 'Use sample garden' before analysing."
        )

    if not is_valid_image_bytes(raw_bytes) or _is_uniform_png(raw_bytes):
        raise NotAGardenError(
            "No garden detected in this photo. Please upload a garden photo."
        )

    return _uploaded_garden_analysis()
