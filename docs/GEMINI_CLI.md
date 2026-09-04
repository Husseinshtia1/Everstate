# Gemini CLI continuity target

Everstate supports Gemini CLI as a native cloud coding-agent destination.

## Install

Gemini CLI's official npm package is `@google/gemini-cli`:

```bash
npm install -g @google/gemini-cli
```

If npm global installs are configured under a user prefix, Everstate also checks common locations such as `~/.npm-global/bin/gemini` and `~/.local/bin/gemini`.

Verify:

```bash
gemini --version
```

## Authentication

Run Gemini CLI interactively and complete one of its supported authentication flows:

```bash
gemini
```

Gemini CLI supports Google login, Gemini API keys, and Vertex AI configuration. Everstate does not store provider credentials.

## Everstate behavior

Interactive continuation uses Gemini CLI's prompt-interactive mode:

```text
gemini -i <everstate continuation prompt>
```

Passive `everstate providers` only checks whether the executable is discoverable because Gemini CLI does not currently expose the same simple local auth-status command used by the Claude Code and Codex adapters.

For stronger verification, opt in to:

```bash
everstate providers --active
```

The active probe runs Gemini CLI headlessly with a fixed health prompt and JSON output. It does not send project state or source code, but it can consume a small amount of provider usage.

## Trust boundary

Everstate never auto-installs Gemini CLI and never starts a provider health request unless the user explicitly chooses active health checks. Provider credentials remain owned by the provider CLI.
