#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require git
require python3

PY_VERSION="$(python3 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Everstate requires Python 3.11 or newer.")
PY

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

echo
echo "Everstate installed in: $ROOT_DIR/.venv"
echo "Python: $PY_VERSION"
echo "Activate with: source .venv/bin/activate"
echo "Verify with: everstate --help"
echo
echo "Codex is not installed by this script. If you want the Claude/other-agent -> Codex continuity test, install the official Codex CLI separately, then run: codex --version"
