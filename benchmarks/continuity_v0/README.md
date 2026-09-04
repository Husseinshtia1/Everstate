# Continuity v0 benchmark

This benchmark measures whether a second AI agent can continue an interrupted task from Everstate state without being manually re-briefed.

## Scenario flow

1. Copy a scenario's `project/` directory to a temporary working directory.
2. Initialize it as a Git repository and commit the interrupted baseline.
3. Seed Everstate with the scenario state:

```bash
everstate acceptance-seed ../scenario.json --path .
```

4. Prepare or launch the target-agent handoff:

```bash
everstate switch codex --path . --dry-run
# or
everstate switch claude --path . --dry-run
```

5. Let the target agent continue the task without any manual re-explanation.
6. Evaluate only observable project outcomes:

```bash
everstate acceptance-evaluate ../scenario.json --path .
```

## What is measured

The evaluator checks deterministic signals such as:

- expected files changed,
- protected files left untouched,
- known-dangerous/failed patterns absent,
- scenario verification commands pass.

The benchmark intentionally does not award credit because an agent *says* it understood the handoff. The repository state must prove it.
