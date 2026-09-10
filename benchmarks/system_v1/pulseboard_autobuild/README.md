# EVR-SYSTEM-001 — Real Full-System Autobuild

EVR-SYSTEM-001 is the first from-scratch build benchmark for the complete Everstate execution path. The input workspace contains only protected evidence (`SPEC.md` and `verify.py`). The primary coding agent must create the application and documentation from Everstate state plus repository evidence.

## What this run exercises

The first release-significant run uses the full chain:

```text
SPEC + verifier
      ↓
Everstate canonical state (CRITICAL)
      ↓
ExecutionFabric participant selection
      ↓
Ruflo AgentCouncil (architect + critic + verifier, debate)
      ↓
advisory council result
      ↓
Everstate continuation packet + advisory result
      ↓
Codex Exec (headless, workspace-write sandbox, network disabled)
      ↓
repository changes
      ↓
Everstate Git evidence refresh
      ↓
deterministic acceptance verifier
      ↓
semantic-state / identity checks
```

Ruflo coordinates the council but does not own canonical project truth. Council output is advisory. Everstate remains authoritative for project identity, objective, current task, decisions, constraints, failed attempts, blockers, next action, and acceptance policy.

## State levels

- `minimal`: objective, current task, next action.
- `standard` (alias `guarded` in the wrapper): minimal plus decisions and constraints.
- `full`: standard plus failed attempts and blockers.
- `critical`: full plus a mandatory independent-council constraint; critical cannot run with the council disabled. **This is the default for EVR-SYSTEM-001.**

A full/critical scenario that omits the required semantic fields is rejected during setup rather than silently pretending that state coverage exists.

## Ubuntu preparation

From the Everstate repository:

```bash
git pull origin main
source .venv/bin/activate
pip install -e '.[dev]'
```

Before the PR is merged, use the feature branch instead:

```bash
git fetch origin
git checkout feat/real-system-acceptance
git pull origin feat/real-system-acceptance
source .venv/bin/activate
pip install -e '.[dev]'
```

Ruflo v3 requires Node 20+:

```bash
node --version
npm install -g 'claude-flow@^3'
everstate ruflo-check
```

Configure the execution fabrics that will supply independent council models:

```bash
everstate setup
```

The real benchmark defaults to a minimum of two eligible council participants. It fails closed rather than silently calling the run "full-system" with only one reviewer.

The first verified headless primary-agent path is Codex. Confirm that the CLI is installed and authenticated:

```bash
codex --version
codex login status
```

Everstate performs `codex login status` before any council/model calls. Codex is then launched through the current non-interactive `codex exec` interface with explicit `workspace-write` sandboxing, `approval_policy="never"`, network disabled for the workspace sandbox, and an ephemeral session. Everstate deliberately does not use legacy convenience flags or disable the sandbox.

## Zero-model preflight

Run this first. It checks Codex authentication, creates a disposable workspace, seeds Everstate state, checks Ruflo and council eligibility, and writes a preview of the primary prompt, but does not call council models and does not launch the coding task:

```bash
EVERSTATE_REAL_DRY_RUN=1 \
EVERSTATE_REAL_RESET=1 \
  bash benchmarks/system_v1/pulseboard_autobuild/run_real.sh \
  "$HOME/everstate-live/EVR-SYSTEM-001" \
  codex \
  critical
```

A successful preflight ends with:

```text
EVR-SYSTEM-001: DRY-RUN READY
```

## First real run

Then run the exact same mission without the dry-run flag:

```bash
EVERSTATE_REAL_RESET=1 \
  bash benchmarks/system_v1/pulseboard_autobuild/run_real.sh \
  "$HOME/everstate-live/EVR-SYSTEM-001" \
  codex \
  critical
```

The wrapper is intentionally thin. The actual orchestration is a first-class Everstate command equivalent to:

```bash
everstate real-accept \
  --scenario benchmarks/system_v1/pulseboard_autobuild/scenario.json \
  --template benchmarks/system_v1/pulseboard_autobuild/project \
  --workspace "$HOME/everstate-live/EVR-SYSTEM-001" \
  --provider codex \
  --state-level critical \
  --council required \
  --orchestrator ruflo \
  --min-council-agents 2
```

## What Pulseboard must build

The coding agent receives an initially clean project containing `SPEC.md` and `verify.py`. It must create:

- `pulseboard.py`
- `README.md`

The resulting CLI must support `add`, `list`, `done`, and `stats`; persist local JSON across separate process runs; preserve monotonically increasing IDs; use atomic replacement for writes; reject invalid IDs/priorities correctly; avoid third-party/network code; and leave `SPEC.md` and `verify.py` untouched.

The verifier generates unpredictable task titles/priorities at runtime, launches the CLI in separate Python processes, checks invalid operations do not rewrite the database, and exercises multiple state transitions. A hard-coded demonstration cannot legitimately pass.

## Evidence retained

Each run keeps evidence under:

```text
<workspace>/.everstate/real-acceptance/
```

Current artifacts include:

- `state-before.json`
- `council-preflight.json`
- `council-result.json` on a real run
- `primary-prompt-preview.txt` on dry-run
- `primary-prompt.txt` on a real run
- `state-after.json`
- `acceptance-report.json`

Acceptance compares repository changes against the immutable `Acceptance baseline` commit as well as the current working tree. Therefore a coding agent cannot hide required changes or protected-file violations by committing them before the verifier runs.

The numeric state version is allowed to advance when Everstate observes new repository evidence. Acceptance instead requires that project identity and the seeded semantic truth remain intact.

## Meaning of PASS

A successful real run must satisfy the deterministic project checks, the primary provider must exit successfully, project identity must be unchanged, semantic state must remain preserved, and the resulting state version must be monotonic.

A PASS proves this specific authenticated run and records which orchestration/provider path participated. It does not imply that every external provider or local runtime has been validated; those are tested separately by repeating the same benchmark with the relevant environment.
