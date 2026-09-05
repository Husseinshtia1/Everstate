# Project Onboarding v1

Everstate source discovery can see local Codex and Claude Code sessions before those working directories are registered as canonical Everstate projects. Project Onboarding turns those discovered working directories into an explicit, user-approved registry step.

## Principles

- Discovery is automatic; registration is explicit.
- Never register every discovered directory silently.
- Only existing local Git repositories are proposed in v1.
- Nested session working directories are normalized to the repository's Git top-level.
- Multiple sessions in the same repository collapse into one project candidate.
- Existing registered projects are shown as REGISTERED and are never duplicated.
- Registration uses Everstate's existing stable project id and `EverstateService.init_project()` path.

## Commands

Inspect candidates from both supported source environments:

```bash
everstate-projects discover
```

Limit discovery to one or more sources:

```bash
everstate-projects discover --from claude-code
everstate-projects discover --from codex --from claude-code
```

Interactively onboard projects:

```bash
everstate-projects onboard
```

The wizard supports:

1. one project
2. selected projects
3. all NEW projects, with a separate bulk confirmation

A second review confirmation is required before registration is written.

List the canonical registry afterwards:

```bash
everstate-projects list
```

## Why this exists

A source session and a canonical project are different identities. A Claude Code session may start in `/repo/src/service`, while another starts in `/repo/tests`; both belong to the same canonical Git project `/repo`. Everstate must establish that canonical identity before transfer planning or source-session association can become reliable.

## Safety boundary

Project onboarding reads source-session metadata already used by Source Discovery and local Git metadata. It does not import prompt/message bodies, does not launch a provider, and does not transfer project state to another environment.
