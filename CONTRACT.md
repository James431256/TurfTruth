# TurfTruth Contract (`CONTRACT.md`)

Single source of truth for all agents across Phase 1 and Phase 2. Adapts the target API and UI test contract to the existing endpoint paths and DOM element IDs in TurfTruth.

---

## 1. Environment & Configuration

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | `""` (unset) | Google Gemini API key (`google-genai` SDK). Never logged or committed. |
| `DEMO_MODE` | `"1"` if `GEMINI_API_KEY` unset | When `"1"` or when `GEMINI_API_KEY` is unset, uses deterministic recorded fixtures from `fixtures/`. |
| `HOURLY_RATE_PENCE` | `2500` (£25.00/hr) | Integer pence per hour used by `pricing.py` and mirrored in frontend JS. |

---

## 2. Gemini Schema & Sanitiser (`ai.py`)

### Pydantic `response_schema` (passed to Gemini)
Gemini estimates work only—never prices, rates, costs, or totals:

```python
class RawTaskEstimate(BaseModel):
    name: str
    hours: float
    evidence: str

class RawGardenAnalysis(BaseModel):
    is_garden: bool
    tasks: list[RawTaskEstimate]
```
*(Compatibility note: `models.py` retains `GeminiTaskEstimate` and `GeminiGardenAnalysisSchema` without any price/cost/total fields.)*

### Server-Side Sanitiser Rules
1. Clamp each task's `hours` to `[0.25, 40.0]` and round to the nearest `0.25`.
2. Drop any task whose stripped `name` or `evidence` is empty.
3. Cap the task list at a maximum of `12` tasks.
4. Assign stable IDs: `"t1"`, `"t2"`, … (`f"t{i}"` for 1-based index `i`).
5. When `is_garden` is `False`, return `tasks = []` and `message = "No garden detected in this photo - nothing to quote."`.
6. Both live Gemini responses and `DEMO_MODE` fixture payloads (`fixtures/sample_garden.json`, `fixtures/not_a_garden.json`) pass through the exact same Pydantic validation + sanitiser pipeline.

---

## 3. HTTP API Contract

Every endpoint is served by FastAPI in `main.py` (with existing route modules in `routes/` preserved and adapted).

### `POST /api/analyse` (and existing `POST /quote/analyse`)
Analyses an uploaded image or the sample garden.
- **Request**:
  - `POST /api/analyse`: `multipart/form-data` with file field `"image"` (or form field `use_sample=true`), OR JSON `{use_sample: bool, image_base64: str | null, filename: str | null}`.
  - `POST /quote/analyse`: JSON `{use_sample: bool, image_base64: str | null, filename: str | null, client_name: str}` (existing route).
- **Success Response (`200 OK` on `/api/analyse`)**:
  ```json
  {
    "is_garden": true,
    "message": null,
    "tasks": [
      {
        "id": "t1",
        "name": "Overgrown lawn mow & edge",
        "hours": 2.0,
        "evidence": "Grass ~15cm tall with creeping border edges."
      }
    ],
    "prompt_version": "analyse_v1",
    "mode": "demo"
  }
  ```
  When `is_garden` is `false` (valid image of a non-garden): returns `200 OK` on `/api/analyse` with:
  ```json
  {
    "is_garden": false,
    "message": "No garden detected in this photo - nothing to quote.",
    "tasks": [],
    "prompt_version": "analyse_v1",
    "mode": "demo"
  }
  ```
- **Error Responses on `/api/analyse`**:
  - `400 Bad Request`: missing file (`code: "no_file"` / `"no_photo"`), empty file, non-image MIME/magic bytes (`code: "invalid_image"`), file > 10 MB (`code: "file_too_large"`).
  - `504 Gateway Timeout`: Gemini timeout at 15s (`code: "ai_timeout"`).
  - `502 Bad Gateway`: Gemini upstream error (`code: "ai_error"`) or schema validation failure (`code: "schema_failure"`).

### `GET /api/calendar` (and existing `GET /calendar`)
Returns the week schedule and working hours (seeded from `data/mock_calendar.json` / `store.py`).
- **Success Response (`200 OK` on `/api/calendar`)**:
  ```json
  {
    "week": [
      {
        "date": "2026-11-23",
        "label": "Mon 23 Nov",
        "rain": true,
        "bookings": []
      },
      {
        "date": "2026-11-24",
        "label": "Tue 24 Nov",
        "rain": false,
        "bookings": [
          {
            "start": "09:00",
            "end": "11:30",
            "title": "Mrs. Patel — Lawn & Borders"
          }
        ]
      }
    ],
    "working_hours": {
      "start": "08:00",
      "end": "17:00"
    }
  }
  ```

### `POST /api/book` (and existing `POST /booking/next`)
Books the earliest valid dry-day gap of duration `hours`.
- **Request (`POST /api/book`)**:
  ```json
  {
    "hours": 4.5
  }
  ```
- **Success Response (`200 OK` on `/api/book`)**:
  - When a slot is found and booked:
    ```json
    {
      "slot": {
        "date": "2026-11-24",
        "start": "11:30",
        "end": "16:00"
      },
      "message": "Booked for Tue 24 Nov, 11:30–16:00."
    }
    ```
  - When no slot fits (e.g. week full or job exceeds working day):
    ```json
    {
      "slot": null,
      "message": "Job duration exceeds a single working day (08:00–17:00)."
    }
    ```
- **Error Response (`400 Bad Request`)**: `hours <= 0`, non-finite, or > 40 (`code: "invalid_hours"`).

### `GET /health`
- **Success Response (`200 OK`)**:
  ```json
  {
    "status": "ok",
    "mode": "demo",
    "prompt_version": "analyse_v1"
  }
  ```

### Standard Error Shape
All `/api/*` error responses return HTTP 4xx/5xx with:
```json
{
  "error": {
    "code": "string_error_code",
    "message": "Human-readable explanation"
  },
  "detail": "Human-readable explanation",
  "code": "string_error_code"
}
```
*(Including top-level `detail` and `code` alongside `error: {code, message}` keeps existing tests and routes in `routes/` 100% compatible with the contract error shape.)*

---

## 4. Domain Module Signatures (`pricing.py`, `scheduler.py`, `ai.py`)

### `pricing.py`
- `HOURLY_RATE_PENCE: int` — read from `os.environ.get("HOURLY_RATE_PENCE", "2500")` (default `2500`).
- `line_cost_pence(hours: float, rate_pence: int = HOURLY_RATE_PENCE) -> int` — validates `hours >= 0` and finite, `rate_pence >= 0`; returns `hours * rate_pence` rounded half-up to the nearest integer penny.
- `total_pence(tasks: Iterable[Mapping[str, Any]], rate_pence: int = HOURLY_RATE_PENCE) -> int` — sums `line_cost_pence(task["hours"], rate_pence)` for all enabled/ticked tasks (`task.get("enabled", True)`).

### `scheduler.py`
- `find_next_slot(duration_hours: float, week: list[dict], working_hours: dict[str, str]) -> tuple[dict[str, str] | None, str | None]` (or returns slot dict / None with reason):
  - Earliest valid contiguous gap within `working_hours["start"]`..`working_hours["end"]`.
  - Never overlaps an existing booking (touching boundaries `end == start` allowed).
  - Never schedules on a day with `rain == True`.
  - Returns `None` if `duration_hours` exceeds a single working day or if no gap is available.

---

## 5. UI `data-testid` & Existing Element ID Mapping

Every required `data-testid` attribute and its corresponding existing element ID (where present in `templates/index.html`):

| `data-testid` | Existing `id` / selector | Element & Requirement |
|---|---|---|
| `sample-btn` | `#sample-btn` | `<button type="button" id="sample-btn" data-testid="sample-btn">Use sample garden</button>` |
| `file-input` | `#photo-input` | `<input type="file" id="photo-input" data-testid="file-input" accept="image/*" />` |
| `analyse-btn` | `#analyse-btn` | `<button type="button" id="analyse-btn" data-testid="analyse-btn">Analyse</button>` |
| `error-msg` | `#error-msg` / `#analyse-msg` | Inline error message element (`data-testid="error-msg"`, `role="alert"`). |
| `demo-badge` | `#demo-badge` | Visible badge when `mode == "demo"` (`data-testid="demo-badge"`). |
| `task-row` | `#quote-tbody tr[data-task-id]` | Each task `<tr>` in the quote table (`data-testid="task-row"`). |
| `task-tick` | `input[data-task-check]` | Task include `<input type="checkbox" data-testid="task-tick" />`. |
| `task-name` | Task name `<td>` | Task name cell (`data-testid="task-name"`). |
| `task-hours` | `input[data-task-hours]` | Hours `<input type="number" min="0" step="0.25" data-testid="task-hours" />`. |
| `task-cost` | `td[data-line-total]` | Formatted £ line cost cell (`data-testid="task-cost"`). |
| `task-evidence` | Visual evidence `<td>` | Short visual evidence note cell (`data-testid="task-evidence"`). |
| `hourly-rate` | `#hourly-rate` | Displayed hourly rate in £ (`data-testid="hourly-rate"`, e.g. `£25.00/hr`). |
| `total` | `#total-gbp` | Displayed total quote price in £ (`id="total-gbp" data-testid="total"`). |
| `book-btn` | `#book-btn` | `<button type="button" id="book-btn" data-testid="book-btn">Book next free slot</button>` |
| `calendar` | `#week-calendar` | Week calendar container (`id="week-calendar" data-testid="calendar"`). |
| `rain-day` | `.day-card.rain-day` | Day card marked as rain (`data-testid="rain-day"`), containing visible `"Rain"` text badge. |
| `existing-booking` | `.slot-block.existing-booking` | Existing booking card on calendar (`data-testid="existing-booking"`). |
| `booked-slot` | `.slot-block.booked-slot` | Newly booked job slot highlighted on calendar (`data-testid="booked-slot"`). |
| `quote-msg` | `#quote-message` | Client quote message `<pre id="quote-message" data-testid="quote-msg">` (tasks, hours, costs, total, booked date). |
| `copy-btn` | `#copy-btn` | `<button type="button" id="copy-btn" data-testid="copy-btn">Copy</button>` -> `"Copied!"` on click. |
