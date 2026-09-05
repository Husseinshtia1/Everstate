# Everstate Transfer Wizard v1

`everstate-transfer` is interactive by default. It must not infer source, project scope, or destination when the user has not supplied them.

## Default flow

```text
Where are you continuing from?
  1. current-worktree
  2. claude-desktop
  3. claude-code
  4. codex
  5. gemini
  6. local
  7. manual
  8. other
```

For Codex and Claude Code, Everstate first offers recent locally discovered sessions and displays their VERIFIED / AMBIGUOUS / UNKNOWN project association. The user may choose a session or select projects directly.

For other sources, Everstate shows the canonical Project Registry and asks for one project, selected projects, or all projects.

`all` always requires a second explicit confirmation.

Then Everstate asks for the destination:

```text
1. Best available (auto)
2. Claude Code
3. Codex
4. Gemini CLI
5. Local Codex + Ollama
6. Portable/manual handoff
7. Custom destination
```

The command ends with a review only. No state or session content is transferred yet.

## Automation mode

For scripts and CI, use `--non-interactive`. Missing choices become errors rather than prompts:

```bash
everstate-transfer \
  --from codex \
  --project proj_example \
  --to gemini \
  --non-interactive
```

No implicit defaults are allowed in non-interactive mode.

## Safety principles

- one project is the default mental model, never all
- all-project transfer needs explicit selection plus confirmation
- session association must be VERIFIED or explicitly resolved by the user
- a project choice cannot silently override VERIFIED session evidence
- source, project scope, and destination are separate dimensions
- wizard interaction creates a plan only; execution is a later gate
