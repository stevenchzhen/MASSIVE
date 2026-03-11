# MASSIVE

MASSIVE is a workspace for building multi-agent, self-healing execution
infrastructure.

The current repository contains the first concrete implementation:

- [`cell/`](/Users/hz/Documents/MASSIVE/cell): a generic task cell that runs a
  task through a structured agent workflow, acquires missing tools through a
  search/install/adapt/create hierarchy, verifies tools deterministically, and
  returns a schema-validated `TaskOutput`

## What Exists Today

The `cell` package includes:

- Temporal workflow orchestration
- Executor, diagnostician, builder, and verifier roles
- Static tools plus dynamic tool acquisition
- Deterministic tool verification
- Caller-defined result schemas
- Configurable trust topologies: `minimal`, `standard`, `high_trust`
- Test coverage for state transitions, agents, sandboxing, verifier behavior,
  and workflow integration

## Repo Layout

```text
MASSIVE/
├── README.md
└── cell/
```

## Start Here

If you want the implementation details, setup steps, and API examples, go to:

- [`cell/README.md`](/Users/hz/Documents/MASSIVE/cell/README.md)

## Status

The repository is currently centered on the single-cell runtime. The larger
multi-cell network layer is not implemented here yet.
