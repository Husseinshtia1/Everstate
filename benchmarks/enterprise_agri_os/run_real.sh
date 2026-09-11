#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCHMARK="$ROOT/benchmarks/enterprise_agri_os"
WORKSPACE="${1:-$HOME/everstate-live/EVR-AGRI-ENTERPRISE-001}"
PROVIDER="${2:-codex}"
# Ruflo is an optional coordination layer, not the canonical execution authority.
# Auto mode prefers Ruflo when healthy and falls back to Everstate's native
# council orchestration if Ruflo fails at runtime. Pass "ruflo" explicitly only
# when validating Ruflo itself and you want failures to be fatal.
ORCHESTRATOR="${3:-auto}"

ARGS=(
  autobuild
  --plan "$BENCHMARK/plan.json"
  --template "$BENCHMARK/template"
  --workspace "$WORKSPACE"
  --provider "$PROVIDER"
  --orchestrator "$ORCHESTRATOR"
  --min-council-agents 2
)

if [[ "${EVERSTATE_REAL_DRY_RUN:-0}" == "1" ]]; then
  ARGS+=(--dry-run)
else
  # A real enterprise acceptance run must prove the generated stack builds and
  # starts, not merely that files exist. The protected verifier consumes this.
  export EVERSTATE_ENTERPRISE_STRICT="${EVERSTATE_ENTERPRISE_STRICT:-1}"
fi

if [[ "${EVERSTATE_REAL_RESET:-0}" == "1" && -e "$WORKSPACE" ]]; then
  case "$WORKSPACE" in
    "$HOME"/everstate-live/*) rm -rf -- "$WORKSPACE" ;;
    *)
      echo "Refusing to reset workspace outside $HOME/everstate-live: $WORKSPACE" >&2
      exit 2
      ;;
  esac
fi

cd "$ROOT"
exec everstate "${ARGS[@]}"
