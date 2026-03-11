# cell

`cell` is a self-healing task cell for structured AI work.

It takes a task, runs it through a multi-agent workflow, builds tools on demand
when the executor gets blocked, verifies those tools deterministically, and
returns a schema-validated `TaskOutput`.

This repo implements a single cell, not the larger network layer.

## What It Does

- Accepts arbitrary task instructions and caller-defined result schemas
- Produces generic `TaskOutput`, not a verification-specific verdict
- Supports trust-level/topology presets: `minimal`, `standard`, `high_trust`
- Dynamically builds missing tools at runtime
- Verifies built tools with static analysis, sandboxed execution, schema checks,
  test cases, edge cases, and fuzzing
- Tracks cost, latency, retries, blockers, and state transitions
- Persists an append-only event log for auditability
- Runs on owned primitives: Temporal, Pydantic, `httpx`, stdlib

## Architecture

The cell has two layers:

1. Task execution
2. Tool self-healing

Happy path:

```text
TaskInput -> Executor -> TaskOutput
```

Self-healing path:

```text
Executor -> Blocker -> Diagnostician -> Builder -> Verifier -> Executor
```

Available topologies:

- `minimal`: executor + combined builder/verifier
- `standard`: executor + combined diagnostician/builder + verifier
- `high_trust`: executor + diagnostician + builder + verifier

The deterministic verifier is always isolated from the builder's reasoning.

## Core Concepts

### TaskInput

The caller defines:

- `instruction`
- `input_data`
- `input_documents`
- `result_schema`
- `result_schema_id`
- `context`
- `trust_level`
- `allow_dynamic_tools`
- `max_cost_usd`

### TaskOutput

The cell returns:

- `result`
- `result_schema_id`
- `confidence`
- `completion_status`
- `sources`
- `reasoning_summary`
- `tools_used`
- `dynamic_tools_created`
- `blockers_encountered`
- `retries`
- `total_latency_ms`
- `total_tokens`
- `total_cost_usd`
- `state_transitions`

## Project Layout

```text
cell/
├── cell/
│   ├── agents/
│   ├── models/
│   ├── output/
│   ├── runtime/
│   ├── tools/
│   ├── api.py
│   ├── config.py
│   ├── hooks.py
│   ├── schema_registry.py
│   └── types.py
├── configs/
├── tests/
├── docker-compose.yaml
└── pyproject.toml
```

## Requirements

- Python 3.12+
- Temporal server
- Optional provider keys:
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
- Optional local model runtime:
  - Ollama on `http://localhost:11434`

## Installation

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run tests:

```bash
pytest -q
```

Current test status in this repo:

```text
68 passed
```

## Running Temporal Locally

Start the local stack:

```bash
docker compose up --build
```

This starts:

- Temporal server
- Temporal UI on `http://localhost:8080`
- Postgres
- A worker running `python -m cell.worker`

## Quick Start

### Python API

```python
from temporalio.client import Client

from cell import Cell, ResultSchemaRegistry


client = await Client.connect("localhost:7233")

result = await Cell.run(
    "Extract all dates and amounts from this invoice",
    client=client,
    documents=["invoice.txt"],
    result_schema=ResultSchemaRegistry.extraction(),
    result_schema_id="extraction",
    trust_level="standard",
)

print(result.result)
print(result.completion_status)
```

### Explicit TaskInput

```python
from temporalio.client import Client

from cell import Cell, TaskInput


client = await Client.connect("localhost:7233")

task = TaskInput(
    task_id="task-001",
    instruction="Review this diff for security issues",
    input_data={"repo": "example/service"},
    input_documents=[],
    result_schema={
        "type": "object",
        "properties": {
            "issues": {"type": "array"},
            "passed": {"type": "boolean"},
        },
        "required": ["issues", "passed"],
    },
    result_schema_id="review",
    context={"severity_threshold": "medium"},
    trust_level="high",
    allow_dynamic_tools=True,
)

output = await Cell.run(task, client=client)
```

### Streaming

```python
async for event in Cell.stream(
    "Analyze this report",
    client=client,
    result_schema=ResultSchemaRegistry.analysis(),
    result_schema_id="analysis",
):
    print(event.event_type, event.data)
```

`Cell.stream()` currently emits lifecycle/state events around workflow
execution. It is not yet true token-by-token or intra-activity live streaming.

## Result Schemas

Use the built-in registry in [`cell/schema_registry.py`](/Users/hz/Documents/MASSIVE/cell/cell/schema_registry.py):

- `verification()`
- `analysis()`
- `generation()`
- `review()`
- `extraction()`
- `custom(schema)`

This keeps the cell generic: the caller owns the output contract.

## Dynamic Tooling

The cell ships with verified static tools:

- calculator
- JSON parser
- CSV reader
- date arithmetic
- statistical tests

When those are insufficient:

1. The executor emits a blocker
2. The diagnostician decides whether to build a tool, request context, or escalate
3. The builder writes a pure Python function
4. The verifier checks it deterministically
5. If verification passes, the tool is registered and execution resumes

## Verification Model

Tool verification is deterministic and does not use an LLM.

Checks include:

- syntax validation
- allowed import enforcement
- network/filesystem/subprocess bans
- sandboxed execution with timeout
- spec test cases
- edge cases
- fuzz inputs generated from JSON Schema
- output schema validation

## Configuration

Default config lives at [`configs/default_cell.yaml`](/Users/hz/Documents/MASSIVE/cell/configs/default_cell.yaml).

Important settings:

- `topology`
- `agents.*.model`
- `limits.max_blockers_per_task`
- `limits.max_tool_build_retries`
- `limits.total_cell_timeout_sec`
- `sandbox.allowed_imports`
- `cost.budget_usd`

You can still load config with:

```python
from cell import load_cell_config

config = load_cell_config("configs/default_cell.yaml")
```

## Hooks

Integration hooks live in [`cell/hooks.py`](/Users/hz/Documents/MASSIVE/cell/cell/hooks.py):

- `on_task_start`
- `on_blocker`
- `on_tool_created`
- `on_result`
- `on_escalation`

Use them to adapt task formats, emit telemetry, or attach external workflow
logic without modifying the core runtime.

## Model Adapters

Supported adapters:

- Anthropic via raw HTTP
- OpenAI via raw HTTP
- Ollama via raw HTTP

No provider SDKs are used.

## Design Constraints

- No LangChain
- No AutoGen
- No CrewAI
- No hidden framework orchestration
- No LLM in the deterministic verification path

## Current Boundaries

- This repo implements a single cell only
- The broader network layer is out of scope
- `Cell.stream()` is event-oriented, not full live reasoning streaming
- Dynamic topology is implemented at config/workflow level; role-specific
  prompt specialization for each combined topology can be expanded further

## Development

Run the full suite:

```bash
pytest -q
```

Run a focused subset:

```bash
pytest tests/test_workflow.py -q
pytest tests/test_verifier.py -q
pytest tests/test_sandbox.py -q
```

## License

Add your project license here.
