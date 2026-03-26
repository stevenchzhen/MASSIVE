# MASSIVE

MASSIVE currently ships the **single-cell foundation only**: a self-healing `cellforge` runtime that runs one task through an executor/diagnostician/builder/verifier loop, verifies installed or generated tools deterministically, and emits replayable local artifacts. The multi-cell network layer is not in this repo yet.

If you want to know whether the repo is usable in under 30 seconds:

```bash
make bootstrap
source .venv/bin/activate
cellforge doctor
```

`doctor` will try to start the local Temporal stack for you when Docker is available; use `cellforge doctor --no-fix` if you only want a passive check.

If `doctor` is green, start the local stack and worker:

```bash
cellforge dev
```

That command will try to connect to Temporal at `localhost:7233`, start the local docker-compose services if possible, and then run the worker in the foreground. The lower-level equivalent is:

```bash
python -m cell.dev
```

## What MASSIVE includes today

- Root-installable `cellforge` package for Python 3.12+
- The tested implementation package under [`/Users/hz/Documents/MASSIVE/cell`](/Users/hz/Documents/MASSIVE/cell)
- A stable CLI: `run`, `stream`, `replay`, `tools list`, `doctor`, `dev`
- Temporal workflow orchestration for a single self-healing cell
- Deterministic tool verification with sandboxed execution
- Local artifact bundles for replay and inspection
- One canonical example task and fixture

## Quickstart

### 1. Bootstrap the repo

```bash
make bootstrap
source .venv/bin/activate
```

If you prefer manual setup, use `python3.12 -m venv .venv` and `pip install -e ".[dev]"`.

### 2. Set provider credentials

```bash
cp .env.example .env
export ANTHROPIC_API_KEY=your_key
```

MASSIVE does not fetch credentials for you. `ANTHROPIC_API_KEY` is the default live provider; `OPENAI_API_KEY` or local Ollama can also be used depending on config.

### 3. Validate local setup

```bash
make doctor
```

`doctor` checks and, if allowed, repairs:

- Python version
- config loading
- Temporal connectivity, with local docker bootstrap when possible
- required provider env vars
- model/provider wiring implied by the config

### 4. Start the local stack and worker

```bash
make dev
```

If Docker is available, this will try to bring up:

- Postgres
- Temporal
- Temporal UI on `http://localhost:8080`

and then start the worker on `cell-task-queue`.

If you want only the infrastructure without the worker:

```bash
make compose-up
```

## Run one real task end to end

The repo ships one narrow example at [`/Users/hz/Documents/MASSIVE/examples/document_extraction`](/Users/hz/Documents/MASSIVE/examples/document_extraction).

Run it with:

```bash
make demo
```

Equivalent direct command:

```bash
cellforge run \
  --example document-extraction \
  --artifacts .artifacts/document-extraction
```

That command will:

- load the bundled invoice-style fixture
- run the task through the cell
- write a replayable artifact bundle to `.artifacts/document-extraction`

Replay the result later with:

```bash
cellforge replay .artifacts/document-extraction
```

Stream lifecycle events for the same example with:

```bash
cellforge stream \
  --example document-extraction \
  --artifacts .artifacts/document-extraction-stream
```

## Self-healing demo

To force the blocker -> build -> verify -> resume path with a restrictive config and a proprietary parsing task:

```bash
make self-heal
```

This runs the staged structure harness in [`/Users/hz/Documents/MASSIVE/scripts/test_structure.py`](/Users/hz/Documents/MASSIVE/scripts/test_structure.py), validates setup, executes a live self-healing task, and checks the artifact bundle for a verified dynamic tool plus a successful completion.

## Artifact bundle format

Each run can emit a local bundle with:

- `input_manifest.json`
- `state_transitions.json`
- `blockers.json`
- `tools_used.json`
- `verifier_report.json`
- `event_log.json`
- `task_output.json`

This is the main inspectability path right now. You can run the task once, keep the bundle, and replay or diff it later without querying Temporal.

## CLI surface

```bash
cellforge run "Extract fields from this document" --document invoice.txt
cellforge stream "Review this input" --document input.txt
cellforge replay .artifacts/some-run
cellforge tools list
cellforge doctor
cellforge dev
```

The CLI is intentionally small. It wraps the existing runtime rather than adding a second abstraction layer.

## Python API

```python
from cellforge import CellForge

cell = CellForge.from_env()
result = cell.run(
    "Extract the invoice number and total amount from this note",
    documents=["examples/document_extraction/invoice_note.txt"],
    artifacts_dir=".artifacts/api-demo",
)
print(result.result)
```

## Repo layout

```text
MASSIVE/
├── pyproject.toml          # root install path
├── README.md               # product entrypoint
├── docker-compose.yaml     # local Temporal stack
├── examples/               # canonical demo + fixtures
├── cell/
│   ├── cell/               # implementation package
│   ├── cellforge/          # public package + CLI shim
│   ├── configs/            # default config
│   └── tests/              # runtime tests
└── CONTRIBUTING.md
```

## Trust boundary

MASSIVE does not claim that a single cell proves its own reasoning. What the current runtime does guarantee is narrower and more honest:

- task results are schema-validated
- tools used by the cell can be verified deterministically
- verifier checks can include task-derived validation samples from the real task inputs when the tool depends on the input shape or format
- the run is auditable through event logs and artifact bundles
- setup failures surface early through `doctor` and fail-closed runtime behavior

Reasoning-level cross-checking belongs in the future network layer, not inside the single cell.

## Independent Context

Context isolation is enforced by role and by payload shape, not by a shared chat transcript.

- The executor sees the task, scoped context, and available tool descriptions.
- The diagnostician sees the blocker plus sampled task data relevant to the blocker, not the full task trace by default.
- The builder sees the `ToolSpec`, optional base tool source, and verifier failure reports on retry, but not the original user task unless it was distilled into the spec.
- The verifier sees only the candidate artifact, the spec, deterministic test cases, and task-derived validation cases. It does not judge narrative reasoning.

This keeps one stage's assumptions from contaminating the next and reduces the blast radius of mistakes.

## Task-derived verifier samples

When a tool is created for a live task, the workflow can derive a bounded sample set from the actual task inputs before diagnosis. This is conditional, not automatic: it is used for data-shape-dependent tools such as parsers, extractors, and normalizers, and skipped for generic helper tools like arithmetic. Today the sampler works generically over text documents, structured `input_data`, and arbitrary records by selecting a deterministic subset guided by the blocker and capped by config:

- `limits.max_task_validation_samples`
- `limits.task_validation_sample_ratio`

Those samples are passed to the diagnostician as scoped evidence. The diagnostician turns the useful ones into exact `task_validation_cases` inside the `ToolSpec`, and the deterministic verifier executes those cases in addition to generic tests, edge cases, regressions, fuzzing, and schema checks.

## Tests

Run the suite from the repo root:

```bash
pytest -q
```

For the structure itself, use the staged runner:

```bash
make quick
python scripts/test_structure.py baseline
make self-heal
```

`quick` proves the orchestration and verifier paths deterministically with mocked workflow tests, `baseline` runs the shipped extraction example end to end, and `self-heal` pressures the live blocker -> build -> verify -> resume path with a restrictive config and a proprietary parsing task. The live phases call `cellforge doctor`, start an ephemeral worker unless you pass `--use-running-worker`, and then validate the emitted artifact bundle.
