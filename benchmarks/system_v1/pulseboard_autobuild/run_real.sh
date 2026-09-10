#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${1:-$HOME/everstate-live/EVR-SYSTEM-001}"
AGENT="${2:-codex}"
STATE_LEVEL="${3:-full}"
MIN_COUNCIL_AGENTS="${EVERSTATE_MIN_COUNCIL_AGENTS:-2}"

OBJECTIVE="Build Pulseboard as a local-only Python CLI that satisfies SPEC.md and passes verify.py without user re-explanation."
TASK="Implement the complete Pulseboard CLI from the canonical project state and repository evidence."
NEXT_ACTION="Read SPEC.md, implement pulseboard.py and README.md, run python verify.py, and repair the implementation until verification exits 0."

case "$STATE_LEVEL" in
  minimal|guarded|full) ;;
  *)
    echo "state level must be one of: minimal, guarded, full" >&2
    exit 2
    ;;
esac

for executable in git python everstate; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    echo "required executable not found: $executable" >&2
    exit 2
  fi
done

case "$AGENT" in
  codex|codex-ollama) AGENT_EXECUTABLE="codex" ;;
  claude) AGENT_EXECUTABLE="claude" ;;
  gemini) AGENT_EXECUTABLE="gemini" ;;
  codex-omniroute) AGENT_EXECUTABLE="omniroute" ;;
  *)
    echo "unsupported primary coding agent: $AGENT" >&2
    echo "supported: codex, claude, gemini, codex-ollama, codex-omniroute" >&2
    exit 2
    ;;
esac

if ! command -v "$AGENT_EXECUTABLE" >/dev/null 2>&1; then
  echo "primary coding-agent executable not found: $AGENT_EXECUTABLE" >&2
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

mkdir -p "$WORKSPACE"
cp "$HERE/SPEC.md" "$WORKSPACE/SPEC.md"
cp "$HERE/verify.py" "$WORKSPACE/verify.py"

# Establish a clean repository baseline. Acceptance checks then distinguish
# files created by the coding agent from protected benchmark evidence.
git -C "$WORKSPACE" init -q
git -C "$WORKSPACE" config user.name "Everstate Acceptance"
git -C "$WORKSPACE" config user.email "acceptance@localhost"
git -C "$WORKSPACE" add SPEC.md verify.py
git -C "$WORKSPACE" commit -q -m "Seed EVR-SYSTEM-001 evidence"

ARTIFACTS="$WORKSPACE/.everstate/real-acceptance"
mkdir -p "$ARTIFACTS"

# Seed canonical state at the requested semantic depth.
everstate init "$WORKSPACE"
everstate set-objective "$OBJECTIVE" --path "$WORKSPACE"
everstate set-task "$TASK" --path "$WORKSPACE"
everstate next "$NEXT_ACTION" --path "$WORKSPACE"

if [[ "$STATE_LEVEL" == "guarded" || "$STATE_LEVEL" == "full" ]]; then
  everstate decide "Use JSON file persistence rather than SQLite" --path "$WORKSPACE"
  everstate decide "Use positive monotonically increasing integer task IDs" --path "$WORKSPACE"
  everstate decide "Use atomic same-directory replacement for every persisted write" --path "$WORKSPACE"
  everstate constraint "Do not modify SPEC.md" --path "$WORKSPACE"
  everstate constraint "Do not modify verify.py" --path "$WORKSPACE"
  everstate constraint "Use Python 3.11+ standard library only" --path "$WORKSPACE"
  everstate constraint "Do not use network access or network libraries" --path "$WORKSPACE"
  everstate constraint "Keep all application data local to the path supplied by --db" --path "$WORKSPACE"
fi

if [[ "$STATE_LEVEL" == "full" ]]; then
  everstate fail "Hard-coding expected verifier outputs is rejected because verification uses fresh temporary databases and multiple process restarts" --path "$WORKSPACE"
  everstate block "No Pulseboard implementation or README exists yet" --path "$WORKSPACE"
fi

everstate packet "$WORKSPACE" --json > "$ARTIFACTS/state-before.json"
everstate status "$WORKSPACE" --json > "$ARTIFACTS/status-before.json"

# A real full-system run requires Ruflo rather than silently accepting native
# orchestration. Council dry-run simultaneously proves at least one execution
# fabric is ready and exposes the exact participants before model calls.
everstate ruflo-check --json > "$ARTIFACTS/ruflo-health.json"

everstate council \
  "Review the Pulseboard implementation mission for correctness, constraint preservation, failure risks, and the shortest evidence-backed path to passing verify.py." \
  --path "$WORKSPACE" \
  --mode debate \
  --rounds 2 \
  --orchestrator ruflo \
  --max-agents 3 \
  --dry-run \
  --json > "$ARTIFACTS/council-plan.json"

python - "$ARTIFACTS/council-plan.json" "$MIN_COUNCIL_AGENTS" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
minimum = int(sys.argv[2])
plan = json.loads(path.read_text(encoding="utf-8"))
participants = plan.get("participants", [])
backend = plan.get("orchestration", {}).get("backend")
if backend != "ruflo":
    raise SystemExit(f"expected Ruflo orchestration, got {backend!r}")
if len(participants) < minimum:
    raise SystemExit(
        f"real acceptance requires at least {minimum} council participants; got {len(participants)}: {participants}"
    )
print(f"Ruflo council preflight: {len(participants)} participants")
PY

# Real multi-agent deliberation. The result is advisory evidence only; it does
# not overwrite canonical project truth.
everstate council \
  "Review the Pulseboard implementation mission for correctness, constraint preservation, failure risks, and the shortest evidence-backed path to passing verify.py." \
  --path "$WORKSPACE" \
  --mode debate \
  --rounds 2 \
  --orchestrator ruflo \
  --max-agents 3 \
  --json > "$ARTIFACTS/council-result.json"

# The primary coding agent receives Everstate's continuation packet through the
# existing crash-safe provider handoff and is allowed to edit the sandbox repo.
everstate start "$TASK" \
  --path "$WORKSPACE" \
  --target "$AGENT" \
  --objective "$OBJECTIVE" \
  --next-action "$NEXT_ACTION" \
  | tee "$ARTIFACTS/primary-agent.log"

everstate packet "$WORKSPACE" --json > "$ARTIFACTS/state-after.json"
everstate status "$WORKSPACE" --json > "$ARTIFACTS/status-after.json"

# Semantic project truth must survive even though repository evidence and the
# numeric state version are allowed to advance during implementation.
python - "$ARTIFACTS/state-before.json" "$ARTIFACTS/state-after.json" "$STATE_LEVEL" <<'PY'
import json
import sys
from pathlib import Path

before = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
after = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
level = sys.argv[3]

fields = ["project_id", "objective", "current_task", "next_action"]
if level in {"guarded", "full"}:
    fields += ["decisions", "constraints"]
if level == "full":
    fields += ["failed_attempts", "blockers"]

mismatches = []
for field in fields:
    if before.get(field) != after.get(field):
        mismatches.append((field, before.get(field), after.get(field)))
if mismatches:
    for field, old, new in mismatches:
        print(f"semantic state changed unexpectedly: {field}: {old!r} -> {new!r}", file=sys.stderr)
    raise SystemExit(1)
print("Canonical semantic state preserved across the coding-agent run")
PY

set +e
everstate acceptance-evaluate "$HERE/scenario.json" --path "$WORKSPACE" --json > "$ARTIFACTS/acceptance-report.json"
ACCEPTANCE_EXIT=$?
set -e

cat "$ARTIFACTS/acceptance-report.json"

echo
echo "Workspace: $WORKSPACE"
echo "State level: $STATE_LEVEL"
echo "Primary agent: $AGENT"
echo "Evidence: $ARTIFACTS"

if [[ $ACCEPTANCE_EXIT -ne 0 ]]; then
  echo "EVR-SYSTEM-001: FAIL" >&2
  exit "$ACCEPTANCE_EXIT"
fi

echo "EVR-SYSTEM-001: PASS"
