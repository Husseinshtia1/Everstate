# Ollama local fallback

Everstate can use Codex CLI as the coding-agent interface while running inference through a local Ollama model.

## Why this path exists

This is an escape hatch for continuity when cloud providers are unavailable, exhausted, or deliberately avoided.

The target key is:

```bash
codex-ollama
```

Everstate treats it as local only when Ollama is reachable on loopback (`127.0.0.1`, `localhost`, or `::1`). A remote `OLLAMA_HOST` is not silently treated as a private local target.

## Requirements

1. Codex CLI installed.
2. Ollama installed and running locally.
3. A compatible model already installed.
4. Enough local memory/resources for that model.

Everstate does **not** download models automatically.

Current Codex OSS mode supports Ollama through its local provider path. For the first controlled Everstate test, `gpt-oss:20b` is the reference model when already installed. Other models can be selected explicitly but may have different Codex tool/model-metadata behavior.

## Model selection

Default reference model:

```text
gpt-oss:20b
```

Override it with an already-installed model:

```bash
export EVERSTATE_OLLAMA_MODEL="qwen3-coder:latest"
```

Everstate verifies the selected model exists through Ollama's local `/api/tags` endpoint before marking the target ready.

## Readiness states

`everstate providers` can report:

- `READY` — Codex exists, local Ollama responds, selected model exists.
- `NOT_INSTALLED` — Codex CLI is unavailable.
- `LOCAL_RUNTIME_UNAVAILABLE` — local Ollama cannot be reached or `OLLAMA_HOST` is non-local.
- `LOCAL_MODEL_MISSING` — selected model is not installed.
- `LOCAL_RESOURCE_INSUFFICIENT` — an active model attempt reports insufficient local memory/resources.

Passive readiness sends no prompt to the model.

## Commands

Passive discovery:

```bash
everstate providers
```

Active local health check:

```bash
everstate providers --active
```

Routing without launch:

```bash
everstate continue --mode local-first --dry-run --path /path/to/project
```

Explicit local target:

```bash
everstate continue --target codex-ollama --path /path/to/project
```

The resulting Codex launch is equivalent in shape to:

```bash
codex --oss --local-provider ollama -m "$EVERSTATE_OLLAMA_MODEL" "<Everstate continuation packet>"
```

## Trust boundary

Provider probes never send project state. The continuation packet is sent only after the user selects or confirms the target.

The local fallback is not claimed to be capability-equivalent to cloud Codex. Everstate routes based on readiness and policy; empirical continuation quality is measured separately by the acceptance harness.
