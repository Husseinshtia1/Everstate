# EVR-REAL-001 — Autonomous Taskboard Build

This is the first real-system Everstate acceptance scenario. It is intentionally small enough to run repeatedly, but it requires an actual coding agent to inspect a repository, preserve constraints, implement persistent behavior, and pass deterministic tests.

## What the run exercises

1. A clean disposable Git workspace is created from `project/`.
2. Everstate seeds canonical project identity and state from `scenario.json`.
3. With `--state-level full`, objective, task, decisions, constraints, failed attempts, blockers, and next action are present.
4. With `--state-level critical`, the full state is used and independent council review is mandatory.
5. AgentCouncil selects eligible models and Ruflo is preferred when ready.
6. Council output is advisory only and is passed to the primary coding agent after canonical state.
7. The primary agent (normally Codex for the first Ubuntu run) edits the workspace.
8. Everstate runs the deterministic acceptance verifier.
9. The run fails if protected tests/policy were changed, required implementation files were not changed, tests fail, provider exits non-zero, project identity changes, constraints change, or the coding agent mutates canonical state.

## Ubuntu preparation

From the Everstate repository:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
npm install -g 'claude-flow@^3'
everstate setup
everstate ruflo-check --json
```

Verify your primary coding agent is authenticated separately. For the first run we use Codex:

```bash
codex --version
```

## Contact-free rehearsal

Use a new workspace path. It must not already contain files.

```bash
rm -rf /tmp/everstate-real-001
everstate real-accept \
  --scenario benchmarks/real_build_v1/taskboard_cli/scenario.json \
  --template benchmarks/real_build_v1/taskboard_cli/project \
  --workspace /tmp/everstate-real-001 \
  --provider codex \
  --state-level full \
  --council required \
  --orchestrator auto \
  --dry-run
```

Dry-run seeds the disposable workspace and Everstate state but must not contact Ruflo council models or the coding provider.

## Real run

Remove the rehearsal workspace first because each run requires a fresh baseline:

```bash
rm -rf /tmp/everstate-real-001
everstate real-accept \
  --scenario benchmarks/real_build_v1/taskboard_cli/scenario.json \
  --template benchmarks/real_build_v1/taskboard_cli/project \
  --workspace /tmp/everstate-real-001 \
  --provider codex \
  --state-level critical \
  --council required \
  --orchestrator auto
```

Success means the final `Everstate Real Acceptance` panel reports `Passed: True` and `Acceptance score: 100%`.

This benchmark does not claim that every external provider is universally reliable. It is specifically designed to reveal live environment failures in Ruflo, execution fabrics, model authentication, coding-agent behavior, state preservation, filesystem behavior, and deterministic project verification.
