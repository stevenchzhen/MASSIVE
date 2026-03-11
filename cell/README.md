# Cell

Reference implementation of a single self-healing verification cell built on
Temporal, Pydantic, `httpx`, and Python standard-library primitives.

## Layout

- `cell/`: runtime, agents, models, tools, and output envelope.
- `configs/default_cell.yaml`: default runtime configuration.
- `tests/`: unit and integration tests.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Temporal

`docker-compose.yaml` starts Temporal, Postgres, the Temporal UI, and a worker
process that serves the cell workflow.

