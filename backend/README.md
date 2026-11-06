# Backend

Python 3.13 project managed with uv. In Step 2 it contains only the pure calculation
core types in `src/samay/core` (standard library only, no runtime dependencies).
The API and database arrive in later steps. See
[../docs/architecture.md](../docs/architecture.md).

```bash
make backend-check        # from the repository root: ruff, mypy --strict, tests + coverage
```

Development tools live only in `backend/.venv`, created from `uv.lock` on first run.
