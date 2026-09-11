#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCHMARK="$ROOT/benchmarks/agri_reliability_v2"
SOURCE_WORKSPACE="${1:-$HOME/everstate-live/EVR-AGRI-ENTERPRISE-001}"
TARGET_WORKSPACE="${2:-$HOME/everstate-live/EVR-AGRI-RELIABILITY-002}"
PROVIDER="${3:-codex}"
ORCHESTRATOR="${4:-auto}"
SOURCE_PLAN="EVR-AGRI-ENTERPRISE-001"
TARGET_PLAN="EVR-AGRI-RELIABILITY-002"
SUMMARY="$SOURCE_WORKSPACE/.everstate/autobuild/$SOURCE_PLAN/summary.json"
SEED="$HOME/everstate-live/.seed-$TARGET_PLAN"

if [[ ! -f "$SUMMARY" ]]; then
  echo "Refusing to start $TARGET_PLAN: enterprise summary not found: $SUMMARY" >&2
  exit 2
fi

python - "$SUMMARY" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
data = json.loads(p.read_text())
if data.get("plan") != "EVR-AGRI-ENTERPRISE-001":
    raise SystemExit("Refusing transition: prerequisite summary is for a different plan")
if data.get("passed") is not True:
    raise SystemExit("Refusing transition: EVR-AGRI-ENTERPRISE-001 has not passed")
stages = data.get("stages") or []
if not stages or any(not s.get("passed") for s in stages):
    raise SystemExit("Refusing transition: not all enterprise stages passed")
if any(int(s.get("attempts", 0)) < 1 for s in stages):
    raise SystemExit("Refusing transition: prerequisite is dry-run-only; every stage must have at least one real implementation attempt")
print(f"Prerequisite verified: {len(stages)} real enterprise stages passed")
PY

if [[ "${EVERSTATE_REAL_RESET:-0}" == "1" ]]; then
  for path in "$SEED" "$TARGET_WORKSPACE"; do
    case "$path" in
      "$HOME"/everstate-live/*) rm -rf -- "$path" ;;
      *) echo "Refusing reset outside $HOME/everstate-live: $path" >&2; exit 2 ;;
    esac
  done
fi

if [[ -e "$TARGET_WORKSPACE" ]] && [[ -n "$(find "$TARGET_WORKSPACE" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  echo "Target workspace must be absent or empty: $TARGET_WORKSPACE" >&2
  exit 2
fi

rm -rf -- "$SEED"
mkdir -p "$SEED"

# Carry the completed product forward as the v2 baseline while dropping runtime
# control state and git metadata. The new autobuild will initialize a fresh
# acceptance git baseline from this product snapshot.
python - "$SOURCE_WORKSPACE" "$SEED" <<'PY'
import shutil, sys
from pathlib import Path
src, dst = map(Path, sys.argv[1:3])
ignore = shutil.ignore_patterns('.git', '.everstate', '__pycache__', '.pytest_cache', 'node_modules', '.next')
for item in src.iterdir():
    if item.name in {'.git', '.everstate', '__pycache__', '.pytest_cache', 'node_modules', '.next'}:
        continue
    target = dst / item.name
    if item.is_dir():
        shutil.copytree(item, target, ignore=ignore)
    else:
        shutil.copy2(item, target)
PY

# Overlay the protected v2 product contract and verifier into the baseline.
cp "$BENCHMARK/template/MASTER_PRODUCT_ENGINEERING_PLAN_V2.md" "$SEED/MASTER_PRODUCT_ENGINEERING_PLAN_V2.md"
cp "$BENCHMARK/template/verify_reliability.py" "$SEED/verify_reliability.py"

ARGS=(
  autobuild
  --plan "$BENCHMARK/plan.json"
  --template "$SEED"
  --workspace "$TARGET_WORKSPACE"
  --provider "$PROVIDER"
  --orchestrator "$ORCHESTRATOR"
  --min-council-agents 2
)

if [[ "${EVERSTATE_REAL_DRY_RUN:-0}" == "1" ]]; then
  ARGS+=(--dry-run)
fi

cd "$ROOT"
exec everstate "${ARGS[@]}"
