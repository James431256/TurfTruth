---
name: scaffold-route
description: Use when adding a new FastAPI endpoint, HTML view, or feature flow in TurfTruth.
---

## Scaffold a TurfTruth route

1. **Models (`models.py`)**: Add typed Pydantic request/response models. Keep any Gemini `response_schema` limited to `task_name`, `estimated_hours`, and `visual_evidence`—put all £ rate/total fields in separate Python-computed models.
2. **State (`store.py`)**: Add in-memory lookup/mutation helpers on the module-level store dict (no DB or ORM).
3. **Route & UI (`routes/<feature>.py`, `templates/`)**: Return either a typed Pydantic model or `templates.TemplateResponse(...)` (vanilla JS only for interactivity). Register the `APIRouter` in `main.py`.
4. **Tests (`tests/test_<feature>.py`)**: Test happy path, edge-case hour adjustments (`<= 0` hours, £ rounding), and typed error responses; mock `google-genai` with `unittest.mock.patch`.
5. **Audit & Verify**: Run the `pricing-audit` subagent and `verify-turftruth` skill before reporting done.
