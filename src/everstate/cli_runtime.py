from __future__ import annotations

import os
from pathlib import Path

from . import cli as _cli


def runtime_home() -> Path:
    configured = os.environ.get("EVERSTATE_HOME", "").strip()
    return Path(configured).expanduser().resolve() if configured else Path.home().resolve()


def runtime_db_path() -> Path:
    return runtime_home() / ".everstate" / "everstate.db"


# The legacy CLI centralizes all state access through cli._db_path().
# Replace that single seam before exposing the Typer app so every command
# (status, mutations, export, continue, etc.) honors EVERSTATE_HOME.
_cli._db_path = runtime_db_path
app = _cli.app
