# Everstate

**Keep working when your AI stops. Keep your project state yours.**

Everstate is an open-source, local-first continuity layer for long-running AI-assisted work. It maintains an evidence-backed current state of a project so you can resume later or move between AI tools without rebuilding context from scratch.

## Product thesis

AI tools remember fragments of the past. Everstate focuses on what is true **now**.

```text
activity -> evidence -> state transitions -> current project state -> continuation context
```

The first product wedge is local continuity between coding agents such as Claude Code and Codex, including interruption/limit rescue.

## Principles

- Local-first by default
- Provider-neutral
- State > chat history
- Evidence > confident prose
- Current > merely similar
- Uncertainty stays visible
- No raw source-code upload is required for local mode
- No account is required for the community/local runtime

## Quick start on Ubuntu

```bash
git clone https://github.com/Husseinshtia1/Everstate.git
cd Everstate
bash scripts/bootstrap_ubuntu.sh
source .venv/bin/activate
everstate --help
```

For the first controlled Claude/other-agent -> Everstate -> Codex acceptance run, follow `docs/UBUNTU_FIRST_RUN.md`.

## Current local prototype

Everstate currently supports local SQLite-backed project state, Git observation, explicit structured state capture, provider-neutral continuation packets, Claude Code/Codex launch adapters, and a deterministic continuity acceptance harness.

```bash
everstate init .
everstate set-objective "Prove cross-AI continuity"
everstate set-task "Fix OAuth callback regression"
everstate decide "Provider B remains active"
everstate constraint "Do not modify database schema"
everstate fail "Provider A fallback duplicated callback handling"
everstate block "Redirect URI test is failing"
everstate next "Run the failing callback test in isolation"
everstate status
everstate resume
everstate packet
everstate switch codex --dry-run
```

`everstate resume` is human-facing. `everstate packet` emits a version-pinned AI-to-AI continuation contract containing current objective/task, decisions, constraints, failed attempts, blockers, modified files, unresolved conflicts, and the next expected action.

## Initial milestones

- **M0 — Truth Before Memory:** local project model, Git observation, immutable events, evidence-backed claims, versioned state.
- **M1 — Resume:** structured objective/task/decision/constraint/failure/blocker state, human Resume, and canonical Continuation Packet.
- **M2 — Cross-agent continuity:** provider adapters plus deterministic acceptance harness for mid-task handoff.
- **M3 — Correct Context:** compile the minimum verified context required for the next task.
- **M4 — Learn From Failure:** preserve failed attempts and warn before unnecessary repetition.

## Status

Very early development. M0 and M1 are merged to `main`; the first M2 deterministic continuity harness is also merged. The next validation step is a real Ubuntu handoff run against native Codex. Everstate remains local-first with no server or account dependency in this phase.

## Licensing direction

Everstate is intended to use an open-source copyleft core with a separate commercial licensing path for proprietary embedding/OEM use. Final licensing terms will be reviewed before the first public release.
