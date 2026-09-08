# Everstate Dual Execution Fabric Acceptance v1

Everstate owns verified project state and continuation truth. OmniRoute and Ypipe are optional execution fabrics with different roles:

- **OmniRoute**: multi-provider/cloud execution, provider/model routing, quota/fallback, protocol translation.
- **Ypipe**: local/air-gapped execution, local models, SmartPipes and MCP integrations.

Neither fabric may mutate canonical Everstate state automatically.

## Required live acceptance sequence

### G0 — Repository and CI baseline
- `main` clean and at expected merge SHA.
- Full Everstate CI green.

### G1 — Isolated OmniRoute preflight
- `everstate omniroute-check --active --json`
- Must report `ready=true`.
- No Claude or other source provider is contacted by the gate.

### G2 — Isolated Ypipe preflight
- `everstate ypipe-check --json`
- Must report at least one local model and `ready=true`.
- With MCP configured: `everstate ypipe-check --mcp --json` must initialize MCP and list tools.
- With inference requested: `everstate ypipe-check --inference --json` must return exactly `EVERSTATE_YPIPE_READY`.

### G3 — Dual fabric preflight
- `everstate fabric-check --require-both --json`
- Must report both fabrics ready.
- Must report `launched_ai_worker=false` and `canonical_state_mutated=false`.

### G4 — Sovereignty routing
Create/use a project with canonical constraint `NO_CLOUD` or `LOCAL_ONLY`.
- `everstate fabric-route --path <project> --json`
- Must select `ypipe` when Ypipe is ready.
- If Ypipe is down, selection must be `null`; OmniRoute must never be used as fallback.

For a project without local-only constraints:
- AUTO should prefer ready local Ypipe.
- If Ypipe is unavailable and OmniRoute is ready, AUTO may select OmniRoute.
- `--mode cloud-preferred` may select OmniRoute unless a canonical local-only constraint exists.

### G5 — Capture-before-Ypipe dry run
- `everstate start <task> --path <project> --target ypipe --dry-run`
- Must persist task/next action first.
- Must write `.everstate/handoffs/state-vN-ypipe.json`.
- Must not contact Ypipe.

### G6 — Verified local continuation
- `everstate ypipe-continue --path <project> --json`
- Response must preserve exact `project_id` and `state_version`.
- Wrong project or stale state version is a hard failure.
- Report must state `canonical_state_mutated=false`.

### G7 — SmartPipe continuation
Configure `EVERSTATE_YPIPE_SMARTPIPE_ENDPOINT` to an operator-published Ypipe SmartPipe.
- SmartPipe receives the structured Everstate continuation envelope.
- SmartPipe response must preserve exact `everstate_project_id` and `everstate_state_version`.
- MCP/file/tool behavior is governed by the SmartPipe/Ypipe operator policy.

### G8 — OmniRoute repository continuation
Repeat the already-proven repository continuation through `codex-omniroute`:
- checkpoint before provider
- real repository identity verification
- branch/HEAD verification
- no packet/repository conflict
- minimal correct work continuation
- targeted tests then full suite

### G9 — Forced cloud failure → sovereign fallback
- Start from a state where cloud execution is allowed.
- Make OmniRoute unavailable without altering Everstate state.
- Ypipe remains ready.
- `fabric-route` must select Ypipe.
- Ypipe continuation must preserve project/state identity.

### G10 — Forced local failure under NO_CLOUD
- Canonical constraint requires local execution.
- Make Ypipe unavailable while OmniRoute remains ready.
- `fabric-route` must select nothing and state that cloud fallback is forbidden.

### G11 — Zero cross-project leakage
Repeat Ypipe/OmniRoute acceptance with two isolated project roots and distinct canary values.
- Project A output must never contain Project B canaries and vice versa.

### G12 — Final regression
- Full `pytest -q` green.
- No unexpected working-tree changes.
- No provider secret appears in Everstate DB, handoffs, logs or config repr.

## Success definition

The dual-fabric integration is considered **live verified** only after G0–G12 pass on real runtimes. CI success alone proves code-level integration, not real Ypipe/OmniRoute runtime availability or end-to-end model behavior.
