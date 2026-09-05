# M2.5I implementation notes

This slice adds the first strict local coding-agent fallback: Codex CLI backed by a localhost Ollama runtime.

Design invariants:

- local means loopback only by default;
- no automatic model download;
- no READY state unless Codex, Ollama, and the selected model are all present;
- local runtime/model/resource failures use local-specific readiness states;
- cloud Codex and local Codex handoff identities remain distinct;
- failure-aware routing re-runs the provider-specific readiness probe;
- `Local First` is a preference, not a bypass of readiness/capability gates;
- `gpt-oss:20b` is the first-test reference model when already installed, while custom local models remain explicit user choices.
