"""Evaluation harness for TurfTruth AI garden analysis pipeline."""

import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ai  # noqa: E402

EVALS_DIR = Path(__file__).resolve().parent
LABELS_PATH = EVALS_DIR / "labels.json"
IMAGES_DIR = EVALS_DIR / "images"
RESULTS_PATH = EVALS_DIR / "RESULTS.md"
FORBIDDEN_KEYS = {"price", "cost", "rate", "total", "gbp", "pence", "amount"}
RUNS_PER_IMAGE = 3


def run_eval_suite() -> dict[str, float | int | str]:
    """Run each labelled image 3 times through ai.analyse_image and write RESULTS.md."""
    cases = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    mode = ai.get_mode() or "demo"
    total_runs = schema_valid = garden_correct = total_tasks = tasks_with_ev = 0
    spreads: list[float] = []
    rows: list[str] = []

    for case in cases:
        img_bytes = (IMAGES_DIR / case["image"]).read_bytes()
        run_hours: list[float] = []
        case_valid = case_acc = 0
        for _ in range(RUNS_PER_IMAGE):
            total_runs += 1
            res = ai.analyse_image(img_bytes, mime_type="image/png", filename=case["image"])
            parsed = ai.AnalysisResult.model_validate(res)
            tasks = (
                res.get("tasks", [])
                if isinstance(res, dict)
                else [t.model_dump() for t in parsed.tasks]
            )
            has_forbidden = any(FORBIDDEN_KEYS & set(t.keys()) for t in tasks)
            if not has_forbidden and len(tasks) >= case["min_tasks"]:
                schema_valid += 1
                case_valid += 1
            if parsed.is_garden == case["is_garden"]:
                garden_correct += 1
                case_acc += 1
            for task in parsed.tasks:
                total_tasks += 1
                tasks_with_ev += int(bool(task.evidence and task.evidence.strip()))
            run_hours.append(sum(t.hours for t in parsed.tasks))

        avg_h = mean(run_hours) if run_hours else 0.0
        spread = ((max(run_hours) - min(run_hours)) / avg_h * 100.0) if avg_h > 0 else 0.0
        if case["is_garden"]:
            spreads.append(spread)
        rows.append(
            f"| `{case['image']}` | `{case['is_garden']}` | {case_valid}/{RUNS_PER_IMAGE} "
            f"| {case_acc}/{RUNS_PER_IMAGE} | {avg_h:.2f}h | {spread:.1f}% |"
        )

    metrics = {
        "mode": mode,
        "prompt_version": ai.PROMPT_VERSION,
        "total_runs": total_runs,
        "schema_validity_pct": (schema_valid / total_runs * 100.0) if total_runs else 0.0,
        "is_garden_accuracy_pct": (garden_correct / total_runs * 100.0) if total_runs else 0.0,
        "hours_spread_pct": mean(spreads) if spreads else 0.0,
        "evidence_coverage_pct": (tasks_with_ev / total_tasks * 100.0) if total_tasks else 100.0,
    }
    report = "\n".join([
        "# TurfTruth AI Evaluation Results",
        "",
        f"- **Execution Mode**: `{metrics['mode']}` | **Prompt Version**: `{metrics['prompt_version']}`",
        f"- **Dataset**: {len(cases)} images × {RUNS_PER_IMAGE} runs = {total_runs} evaluations",
        "",
        "| Metric | Target | Result |",
        "|---|---|---|",
        f"| Schema Validity & Zero-Pricing Guard | 100.0% | {metrics['schema_validity_pct']:.1f}% |",
        f"| `is_garden` Classification Accuracy | >= 95.0% | {metrics['is_garden_accuracy_pct']:.1f}% |",
        f"| Hours Spread `(max-min)/mean` | <= 15.0% | {metrics['hours_spread_pct']:.1f}% |",
        f"| Tasks with Non-Empty Visual Evidence | 100.0% | {metrics['evidence_coverage_pct']:.1f}% |",
        "",
        "| Image | Expected `is_garden` | Schema Valid | Accuracy | Mean Hours | Hours Spread |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
    ])
    RESULTS_PATH.write_text(report, encoding="utf-8")
    print(report)
    return metrics


if __name__ == "__main__":
    run_eval_suite()
