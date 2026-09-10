#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCHMARK="$ROOT/benchmarks/enterprise_agri_os"
WORKSPACE="${1:-$HOME/everstate-live/EVR-AGRI-ENTERPRISE-001}"
PROVIDER="${2:-codex}"
ORCHESTRATOR="${3:-ruflo}"

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
