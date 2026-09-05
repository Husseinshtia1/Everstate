# Everstate Capture-First Failover v1

## Goal

Make continuation independent of the source AI at the exact moment that provider becomes unavailable because of a usage limit, outage, auth failure, or process crash.

## Invariant

> Failover MUST NOT require any prompt, summary, API call, health probe, or other cooperation from the unavailable source provider.

## Flow

```text
AI work surface
  -> everstate_capture (minimal structured facts)
  -> local append-only event store
  -> canonical ProjectState
  -> source becomes unavailable
  -> everstate-emergency-failover
  -> integrity-checked continuation bundle
  -> destination adapter / provider
```

## Capture surface

`everstate-mcp` is a local stdio MCP server. It exposes two tools:

- `everstate_capture`
- `everstate_status`

Capture kinds are intentionally narrow:

- objective
- task
- decision
- constraint
- failure
- blocker
- next_action

Raw full conversation transcripts are not a default capture primitive. Structured values are capped at 8,000 characters and NUL bytes are rejected.

The source provider is recorded as provenance only. It never owns canonical state.

## MCP compatibility

The server accepts the established `initialize` flow for older MCP clients and also exposes `server/discover` for the 2026-07-28 stateless protocol generation. Tool operations remain ordinary JSON-RPC `tools/list` and `tools/call` requests over stdio.

## Emergency failover

Example:

```bash
everstate-emergency-failover \
  --path /path/to/project \
  --source claude \
  --target codex
```

The command writes outside the project by default under:

```text
~/.everstate/failovers/<timestamp>-<project-id>-<target>/
```

Artifacts:

- `continuation.json`
- `continuation.md`
- `manifest.json`

The manifest includes SHA-256 hashes and records `source_contacted=false`.

## Required acceptance gates

Before calling this capability proven on a real provider:

1. At least two projects with deliberately conflicting marker state.
2. Capture state independently for each project.
3. Simulate source provider unavailable.
4. Build failover bundle for Project A.
5. Project B markers must be absent from Project A bundle.
6. Source provider calls during failover must equal zero.
7. Destination receives the correct project identity, objective, constraints, failures, and next action.
8. No success claim is made merely because a destination process exits with code 0.

## Current scope

This v1 establishes capture, canonical-state independence, isolation, and source-independent bundle generation. Destination launch remains handled by the existing Everstate continuation/routing layer; a real source-dead -> destination-live acceptance run is the next empirical gate.
