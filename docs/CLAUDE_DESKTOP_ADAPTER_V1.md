# Claude Desktop Source Adapter v1

## Purpose

Claude Desktop is an independent source environment. Everstate must never substitute Claude Code sessions or the canonical Everstate project registry and present those items as if they were projects inside Claude Desktop.

Invariant:

> Source inventory must come from the selected source.

For `claude-desktop`, v1 reads only local Claude Desktop/Cowork project metadata from the Desktop `spaces.json` store.

## Current local contract

Everstate probes the current Desktop/Cowork layout:

- Linux: `~/.config/Claude/local-agent-mode-sessions/<account>/<org>/spaces.json`
- macOS: `~/Library/Application Support/Claude/local-agent-mode-sessions/<account>/<org>/spaces.json`
- Windows: `%APPDATA%/Claude/local-agent-mode-sessions/<account>/<org>/spaces.json`

`EVERSTATE_CLAUDE_DESKTOP_ROOT` can override the root for diagnostics/tests.

The adapter reads only bounded JSON project metadata. It extracts:

- Desktop project/space id
- project name/title
- local folder assignments when present
- account/org path identifiers
- metadata storage path

It deliberately does **not** ingest:

- conversation bodies
- prompts or responses
- project instructions
- memory contents
- arbitrary renderer/IndexedDB state

## Canonical mapping

A Claude Desktop project and an Everstate canonical project are different identities.

The selected Desktop project is mapped to canonical Everstate state only when local folder evidence uniquely matches one registered canonical project.

Statuses:

- `VERIFIED`: exactly one canonical project matches the Desktop folder evidence
- `AMBIGUOUS`: multiple canonical projects match; Everstate refuses to guess
- `UNKNOWN`: no local folder is exposed or no canonical project matches

For `AMBIGUOUS`/`UNKNOWN`, interactive transfer requires the user to explicitly select and confirm a canonical project mapping for that transfer.

## CLI

Inspect only actual Desktop/Cowork local source inventory:

```bash
everstate-desktop projects --full-paths
```

JSON diagnostic output:

```bash
everstate-desktop projects --json
```

Interactive transfer:

```bash
everstate-transfer
```

Selecting `claude-desktop` now displays actual Desktop source inventory first. If none is found, the command fails rather than falling back to Claude Code sessions or registered Everstate projects.

## Boundary

This v1 adapter covers local Claude Desktop/Cowork projects represented by the local `spaces.json` contract. It does not claim complete inventory of account/cloud-only claude.ai projects that expose no local Desktop project metadata. Those require a separate verified cloud/account adapter in a later milestone.
