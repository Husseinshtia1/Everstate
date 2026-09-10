#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${1:-$HOME/everstate-live/EVR-SYSTEM-001}"
AGENT="${2:-codex}"
STATE_LEVEL="${3:-critical}"
MIN_COUNCIL_AGENTS="${EVERSTATE_MIN_COUNCIL_AGENTS:-2}"

case "$STATE_LEVEL" in
  guarded) CLI_STATE_LEVEL="standard" ;;
  minimal|standard|full|critical) CLI_STATE_LEVEL="$STATE_LEVEL" ;;
  *)
    echo "state level must be one of: minimal, guarded, standard, full, critical" >&2
    exit 2
    ;;
esac

for executable in git python everstate; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    echo "required executable not found: $executable" >&2
    exit 2
  fi
done

# EVR-SYSTEM-001 is deliberately strict. Everstate currently verifies Codex
# as the headless primary implementation path via `codex exec --full-auto`.
# Other adapters remain available for interactive handoff, but they must not
# be advertised as automated acceptance providers until their headless
# contracts have their own live validation.
if [[ "$AGENT" != "codex" ]]; then
  echo "EVR-SYSTEM-001 currently supports only the verified headless provider: codex" >&2
  exit 2
fi

if [[ "${EVERSTATE_REAL_DRY_RUN:-0}" != "1" ]] && ! command -v codex >/dev/null 2>&1; then
  echo "primary coding-agent executable not found: codex" >&2
  exit 2
fi

if [[ -e "$WORKSPACE" ]]; then
  if [[ "${EVERSTATE_REAL_RESET:-0}" != "1" ]]; then
    echo "workspace already exists: $WORKSPACE" >&2
    echo "Choose another path or set EVERSTATE_REAL_RESET=1 to recreate it." >&2
    exit 2
  fi
  rm -rf "$WORKSPACE"
fi

# This benchmark intentionally requires Ruflo. A missing Ruflo installation is
# a preflight failure, not permission to silently downgrade the acceptance run.
everstate ruflo-check

ARGS=(
  --scenario "$HERE/scenario.json"
  --template "$HERE/project"
  --workspace "$WORKSPACE"
  --provider "$AGENT"
  --state-level "$CLI_STATE_LEVEL"
  --council required
  --orchestrator ruflo
  --min-council-agents "$MIN_COUNCIL_AGENTS"
)

if [[ "${EVERSTATE_REAL_DRY_RUN:-0}" == "1" ]]; then
  ARGS+=(--dry-run)
fi

echo "EVR-SYSTEM-001"
echo "Workspace: $WORKSPACE"
echo "Primary coding agent: $AGENT (headless)"
echo "State level: $CLI_STATE_LEVEL"
echo "Minimum council participants: $MIN_COUNCIL_AGENTS"
echo

everstate real-accept "${ARGS[@]}"

if [[ "${EVERSTATE_REAL_DRY_RUN:-0}" == "1" ]]; then
  echo "EVR-SYSTEM-001: DRY-RUN READY"
else
  echo "EVR-SYSTEM-001: completed; inspect the PASS/FAIL checks above and $WORKSPACE/.everstate/real-acceptance/"
fi
