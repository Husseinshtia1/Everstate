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

# The enterprise benchmark is intentionally operator-light. On the first run,
# try to discover existing fabrics and install the supported free remote fabric
# when it is missing. This preserves the saved execution policy and never
# weakens local-only constraints. Setup may still return 2 when a service needs
# operator credentials/configuration; autobuild then performs its own strict
# preflight and prints the remaining blocker.
if [[ "${EVERSTATE_AUTOBUILD_BOOTSTRAP:-1}" == "1" ]]; then
  echo "Everstate: checking execution fabrics before enterprise autobuild..."
  if ! everstate setup --yes --install-missing --no-browser; then
    echo "Everstate: automatic execution bootstrap did not find a ready fabric; continuing to strict autobuild diagnostics." >&2
  fi
fi

exec everstate "${ARGS[@]}"
