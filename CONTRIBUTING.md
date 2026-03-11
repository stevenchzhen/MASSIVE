# Contributing

MASSIVE currently ships the single-cell CellForge foundation. Keep changes small, testable, and inspectable.

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## What to contribute

- Fixes that improve usability, inspectability, or runtime safety.
- Tests that lock in current behavior.
- New tools with deterministic test coverage and clear schemas.

## Tool contributions

Add tool implementations under `cell/cell/tools/static/` and include focused tests under `cell/tests/`.
