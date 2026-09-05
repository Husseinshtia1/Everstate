# Everstate Source Discovery v1

## Goal

Discover local AI sessions without importing conversation bodies, then associate each session with a canonical Everstate project before any transfer can occur.

## Supported discovery sources

### Codex

Everstate scans local JSONL session files under `~/.codex/sessions/` and reads only a bounded metadata prefix to find working-directory evidence.

### Claude Code

Everstate scans top-level JSONL session files under `~/.claude/projects/<project>/` and reads only a bounded metadata prefix to find working-directory evidence.

### Claude Desktop

Claude Desktop is intentionally **not** treated as equivalent to Claude Code. Everstate does not currently claim a stable local discovery contract for all Claude Desktop projects/conversations. Until a supported adapter exists, Claude Desktop source selection requires an explicit project association rather than automatic discovery.

## Privacy rule

Discovery is metadata-only. Everstate does not read or import prompt/message bodies to decide project identity.

The metadata reader is bounded by line count and byte count and looks only for path fields such as `cwd`, `projectPath`, or `project_path`.

## Association states

### VERIFIED

A session can be associated automatically only when its working directory uniquely matches one registered Everstate project, either exactly or as a unique descendant of that project root.

### AMBIGUOUS

If the session path matches more than one registered project, Everstate must not guess. The user must select the project explicitly.

### UNKNOWN

If no working directory is available, or no registered project matches it, the session remains unknown until the user associates it manually.

## CLI

```bash
everstate-sources --from codex

everstate-sources --from claude-code
```

Machine-readable:

```bash
everstate-sources --from codex --json
```

## Safety invariants

1. Session discovery never means transfer.
2. No session with `AMBIGUOUS` or `UNKNOWN` association may be transferred automatically.
3. Claude Desktop must not silently reuse Claude Code discovery semantics.
4. Prompt/message bodies are not required for project identity discovery.
5. Project identity remains canonical in Everstate; provider sessions are evidence linked to that identity.
6. Wrong-project association is treated as more dangerous than missing association.
