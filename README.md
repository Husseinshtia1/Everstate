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

## Initial milestones

- **M0 — Truth Before Memory:** local project model, Git observation, immutable events, evidence-backed claims, versioned state.
- **M1 — Resume:** reconstruct where a project currently stands and what changed.
- **M2 — Cross-agent continuity:** hand off work between Claude Code and Codex.
- **M3 — Correct Context:** compile the minimum verified context required for the next task.
- **M4 — Learn From Failure:** preserve failed attempts and warn before unnecessary repetition.

## Status

Very early development. The repository is being built as a local-first open-source project before any optional hosted services are introduced.

## Licensing direction

Everstate is intended to use an open-source copyleft core with a separate commercial licensing path for proprietary embedding/OEM use. Final licensing terms will be reviewed before the first public release.
