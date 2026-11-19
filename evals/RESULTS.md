# TurfTruth AI Evaluation Results

- **Execution Mode**: `demo` | **Prompt Version**: `analyse_v1`
- **Dataset**: 5 images × 3 runs = 15 evaluations

| Metric | Target | Result |
|---|---|---|
| Schema Validity & Zero-Pricing Guard | 100.0% | 100.0% |
| `is_garden` Classification Accuracy | >= 95.0% | 100.0% |
| Hours Spread `(max-min)/mean` | <= 15.0% | 0.0% |
| Tasks with Non-Empty Visual Evidence | 100.0% | 100.0% |

| Image | Expected `is_garden` | Schema Valid | Accuracy | Mean Hours | Hours Spread |
|---|---|---|---|---|---|
| `garden_01_overgrown_lawn.png` | `True` | 3/3 | 3/3 | 5.50h | 0.0% |
| `garden_02_hedges_and_patio.png` | `True` | 3/3 | 3/3 | 5.50h | 0.0% |
| `garden_03_backyard_borders.png` | `True` | 3/3 | 3/3 | 5.50h | 0.0% |
| `not_a_garden_01_indoor.png` | `False` | 3/3 | 3/3 | 0.00h | 0.0% |
| `not_a_garden_02_blank.png` | `False` | 3/3 | 3/3 | 0.00h | 0.0% |
