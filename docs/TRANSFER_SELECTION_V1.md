# Everstate Transfer Selection v1

## Problem

A continuation transfer is unsafe if Everstate knows only the destination. A user may have multiple projects across Claude Desktop, Claude Code, Codex, Gemini, local tools, or other environments. Everstate must never infer that every project should move, and it must not mix state between projects.

## Required transfer identity

Every transfer plan has three independent dimensions:

1. **Source environment** — where the user is continuing from.
2. **Project scope** — exactly which project or projects are being transferred.
3. **Destination environment** — where the selected project state should continue.

No transfer may execute without all three being resolved.

## Source environments

Initial source identities:

- `current-worktree`
- `claude-desktop`
- `claude-code`
- `codex`
- `gemini`
- `local`
- `manual`
- `other`

A source environment is not the same thing as a project. The same Git project may have sessions in several AI environments.

## Project identity

The canonical project identity in v1 is the Everstate project registry:

- stable Everstate project id
- project name
- canonical root path

This prevents a Claude session title, Codex session label, or chat title from becoming the project identity by accident.

Provider/session adapters may later discover evidence that links a session to a registered project, but they must not silently create cross-project associations.

## Project scope

Everstate supports exactly three scopes:

- `single` — one explicitly selected project; default intended UX.
- `selected` — multiple explicitly selected projects.
- `all` — every registered project, only after an explicit bulk-selection action and a second confirmation.

Everstate must never interpret an omitted project selector as `all`.

## UX contract

The interactive flow should be:

```text
Where are you continuing from?
  Claude Desktop
  Claude Code
  Codex
  Gemini
  Local AI
  This folder
  Other

Which project do you want to continue?
  [ ] Everstate
  [ ] Ayneye
  [ ] Tynixa
  [ ] ...

  Select one
  Select several
  Select all projects

Where do you want to continue?
  Best available
  Claude Code
  Codex
  Gemini
  Local AI
  Manual export

Review
  Source: Claude Desktop
  Projects: Everstate only
  Destination: Gemini

Continue?
```

For `Select all projects`, Everstate shows a second warning and confirmation before any state leaves the source scope.

## Non-interactive contract

The deterministic CLI planning surface is:

```bash
everstate-transfer \
  --from claude-desktop \
  --project proj_abc123 \
  --to gemini
```

Multiple projects:

```bash
everstate-transfer \
  --from codex \
  --project proj_alpha \
  --project proj_beta \
  --to claude-code
```

All projects requires explicit double opt-in:

```bash
everstate-transfer \
  --from codex \
  --all \
  --confirm-all \
  --to gemini
```

The initial command only builds and displays a transfer plan; it does not move state. Execution will be added after source/session adapters prove project identity.

## Discovery vs identity

Everstate must distinguish:

- **Project registry:** canonical project identity owned by Everstate.
- **Source discovery:** sessions/workspaces found inside a provider environment.
- **Association:** evidence linking a discovered provider session to a canonical Everstate project.

Claude Desktop, Claude Code, Codex, and other providers may expose projects or sessions differently. A provider-specific session title is never enough by itself to merge project state.

## Safety invariants

1. No implicit bulk transfer.
2. No destination launch before source and project scope are visible to the user.
3. No cross-project state merging based on similar names.
4. Project ids outrank provider session labels.
5. Ambiguous project names require project-id selection.
6. Bulk transfer requires a second explicit confirmation.
7. A transfer plan is reviewable before execution.
8. Source adapters may discover sessions but may not mutate canonical project identity directly.
9. The same project can exist in multiple AI environments without becoming multiple Everstate projects.
10. If project/source association confidence is insufficient, Everstate asks the user instead of guessing.

## Next implementation layer

After this contract, provider-specific source adapters can implement:

`discover(source) -> source sessions/workspaces`

then:

`associate(source session, Everstate project) -> VERIFIED / AMBIGUOUS / UNKNOWN`

Only VERIFIED associations may support one-click transfer. AMBIGUOUS and UNKNOWN associations require user selection.
