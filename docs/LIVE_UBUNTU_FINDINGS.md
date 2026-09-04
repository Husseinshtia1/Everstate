# Live Ubuntu findings

The first real Ubuntu continuity run exposed two runtime issues before the target agent launched:

1. Codex had been installed successfully in `~/.npm-global/bin`, but Everstate only checked `PATH`. Provider discovery now also checks common user-level install locations and supports `EVERSTATE_CODEX_BIN` / `EVERSTATE_CLAUDE_BIN` overrides.
2. `.everstate/` handoff artifacts and Python cache files appeared in `git status` and polluted acceptance output. Acceptance diffing now ignores Everstate-internal state and Python cache artifacts.

The observed 60% acceptance result from that run is not treated as a continuity result because Codex never launched. The scenario must be rerun after these runtime fixes before drawing any product conclusion.
