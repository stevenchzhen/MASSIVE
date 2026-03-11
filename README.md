**Self-healing AI execution with adversarial tool verification.**

[![PyPI version](https://img.shields.io/pypi/v/cellforge.svg)](https://pypi.org/project/cellforge/) [![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) [![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/) [![Tests passing](https://img.shields.io/badge/tests-passing-brightgreen.svg)](#)

## The 15-second hook

MASSIVE, published as `cellforge`, is a Python runtime for self-healing AI execution that handles capability gaps without defaulting to unchecked agent improvisation. What makes it different is a fail-closed build path with role separation, scoped context, and a deterministic verifier, so failures and assumptions do not cascade across stages. The cell never silently fails — it either builds what it needs or tells you why it can't.

## Terminal recording placeholder

`[GIF: cell hits blocker → diagnostician specs tool → builder writes it → verifier runs tests → executor resumes]`

![CellForge terminal recording](docs/terminal-recording.gif)
<!-- TODO: replace with real terminal recording -->

## Install + first run

```bash
pip install cellforge
```

Set `CELLFORGE_API_KEY` in your environment, then run:

```python
from cellforge import CellForge
cell = CellForge.from_env()
result = cell.run("Extract invoice dates and totals from this CSV")
print(result.result)
print(result.completion_status)
```

## How it works

```text
executor -> blocker -> diagnostician -> builder -> verifier
    ^                                                   |
    |---------------------- tool ready -----------------|
```

Execution starts in the executor; on a blocker, the diagnostician decides whether to reuse, install, adapt, or create a tool, the builder works from a scoped spec instead of the full task, and the verifier resumes execution only after deterministic checks pass.

Separation matters because the agent that needs a tool never builds it, each stage receives scoped context only, the builder does not see the full task unless explicitly required, and the deterministic verifier checks the candidate against the spec and tests to reduce blast radius and prevent one stage's assumptions from contaminating the next.

## Trust levels

| Level | Topology | Description |
| --- | --- | --- |
| `minimal` | 2 agents: executor + combined builder/verifier | Fastest and cheapest, with reduced separation for lower-stakes runs. |
| `standard` | 3 agents: executor + combined diagnostician/builder + verifier | Default mode for production workflows that need verified tool acquisition without maximum overhead. |
| `high-trust` | 4 agents: executor + diagnostician + builder + verifier | Full separation with minimal context handoff for workflows where trust and auditability matter most. |

## Tool acquisition pipeline

CellForge resolves capability gaps in this order: 1. search local, 2. search public registry, 3. adapt existing, 4. build from scratch; each step is more expensive than the last, and CellForge only escalates when cheaper options fail.

## Bundled tools

| Tool | Description |
| --- | --- |
| `precise_math` | Deterministic arithmetic, percentages, rates, and bounded numeric transforms. |
| `csv_processor` | Parses CSV inputs, filters rows, and computes practical column summaries. |
| `json_schema_check` | Validates structured outputs and catches shape mismatches early. |
| `table_diff` | Compares tabular datasets and highlights row and field-level changes. |
| `statistics` | Runs common descriptive statistics and lightweight test calculations. |
| `document_text` | Extracts normalized text from document-like inputs for downstream tools. |
| `hash_file` | Produces content hashes for provenance and auditable artifact tracking. |

```bash
cellforge tools install-pack financial
```

Domain packs add verified tool bundles without changing the runtime model.

## Streaming

```python
async for event in cell.stream(
    "Review this diff for security issues",
    result_schema="review",
):
    print(event.type, event.data)
```

```text
state_changed -> {"from":"executing","to":"diagnosing"}
blocker.detected -> {"category":"missing_capability","description":"No matching tool"}
tool.verified -> {"tool_id":"table_diff","passed":true}
cell.complete -> {"completion_status":"complete","confidence":0.94}
```

## Configuration

```yaml
executor_model: claude-sonnet-4-5      # primary execution model
diagnostician_model: gpt-4o            # scoped blocker analysis
builder_model: claude-sonnet-4-5       # tool synthesis or adaptation
verifier: deterministic                # no LLM in verification
trust_level: standard                  # 3-agent default
limits:
  max_blockers: 5                      # fail-closed after repeated gaps
  max_tool_retries: 2                  # rebuild/adapt attempts per tool
  total_timeout_sec: 1800              # hard wall-clock cap
cost:
  budget_usd: 5.00                     # stop before spend drifts
  alert_threshold_usd: 3.00            # early warning threshold
```

## How is this different?

| Capability | LangGraph | SmolAgents | Agent Zero | CellForge |
| --- | --- | --- | --- | --- |
| Runtime tool creation | X | ✓ | ✓ | ✓ |
| Separated build/verify pipeline | X | X | X | ✓ |
| Context isolation between stages | X | X | X | ✓ |
| Deterministic verification (no LLM) | X | X | X | ✓ |
| Builder blind to task | X | X | X | ✓ |
| Auditable tool artifacts | X | X | X | ✓ |

## Use cases

- Financial document analysis where missing parsing or reconciliation capability has to be added without trusting unchecked generated code.
- Scientific claim verification where provenance, reproducibility, and fail-closed execution matter more than agent latency alone.
- Code review workflows that need verified helper tools instead of opaque tool-calling behavior.
- Data extraction pipelines that must handle unknown formats while reducing silent failure and preserving auditable artifacts.

## OpenClaw integration

`openclaw skills install cellforge`
`cellforge run "Review this reconciliation CSV" --trust standard`
done

## Benchmarks

| Test Suite | Raw LLM | Tool-Calling Agent | CellForge |
| --- | --- | --- | --- |
| Reconciliation accuracy | TODO | TODO | TODO |
| Unknown format completion | TODO | TODO | TODO |
| Silent failure rate | TODO | TODO | TODO |
| Audit trail reproducibility | TODO | TODO | TODO |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

The easiest way to contribute is adding a tool to the registry: write a function, write 3 test cases, submit a PR, and CI verifies it automatically.

## License

This project is licensed under the MIT License.
