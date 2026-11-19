---
name: verify-turftruth
description: Run this to execute deterministic boundary checks on schema isolation, module line limits, and live HTTP endpoints before finishing a feature.
---

## TurfTruth deterministic boundary checks

1. **Module size gate**: `find . -name '*.py' -not -path './.venv/*' -exec wc -l {} + | awk '$1 >= 200 && $2 != "total" {print; err=1} END {exit err}'` (fails if any module hits 200 lines and needs splitting into `routes/`, `services/`, `store.py`, or `models.py`).
2. **Gemini schema pricing gate**: `uv run python -c "import ast, pathlib, sys; trees=[ast.parse(p.read_text()) for p in pathlib.Path('.').rglob('*.py') if '.venv' not in p.parts]; used={k.value.id for t in trees for n in ast.walk(t) if isinstance(n, ast.Call) for k in n.keywords if k.arg=='response_schema' and isinstance(k.value, ast.Name)}; bad=[n.name for t in trees for n in ast.walk(t) if isinstance(n, ast.ClassDef) and (n.name in used or 'Schema' in n.name) for s in n.body if isinstance(s, ast.AnnAssign) and getattr(s.target, 'id', '').lower() in {'price','total','cost','rate','gbp','subtotal'}]; sys.exit('Schema leak: '+','.join(bad) if bad else 0)"`.
3. **Live route smoke test with teardown**: `uv run uvicorn main:app --port 8080 & PID=$!; trap "kill $PID 2>/dev/null" EXIT; sleep 1; curl -sf http://127.0.0.1:8080/health >/dev/null && curl -sf http://127.0.0.1:8080/ >/dev/null`.
