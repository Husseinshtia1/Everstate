from __future__ import annotations

import os
from pathlib import Path

from . import cli as _cli
from .council_cli import register as register_council
from .fabric_check_cli import register as register_fabric_check
from .fabric_continue_cli import register as register_fabric_continue
from .fabric_route_cli import register as register_fabric_route
from .omniroute_check_cli import register as register_omniroute_check
from .ruflo_cli import register as register_ruflo
from .setup_wizard_cli import register as register_setup
from .work_start_cli import register as register_work_start
from .ypipe_check_cli import register as register_ypipe_check
from .ypipe_continue_cli import register as register_ypipe_continue


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

# Register additive runtime-aware workflows without changing legacy command behavior.
register_setup(app)
register_work_start(app, _cli._service)
register_council(app, _cli._service)
register_ruflo(app)
register_omniroute_check(app)
register_ypipe_check(app)
register_fabric_route(app, _cli._service)
register_fabric_continue(app, _cli._service)
register_ypipe_continue(app, _cli._service)
register_fabric_check(app)
