from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .execution_config import configured_policy, fabric_enabled
from .fabric_routing import SovereigntyMode, choose_execution_fabric
from .freellmapi_fabric import FreeLLMAPIFabric
from .omniroute_fabric import OmniRouteFabric
from .provider_fabric import FabricHealth
from .service import EverstateService
from .ypipe_fabric import YpipeFabric

console = Console()


def _safe_health(name: str, factory) -> FabricHealth:
    if not fabric_enabled(name):
        return FabricHealth(status="DISABLED", ready=False, detail="Disabled by Everstate setup policy.")
    try:
        return factory().health()
    except (ValueError, OSError, RuntimeError) as exc:
        return FabricHealth(status="UNAVAILABLE", ready=False, detail=str(exc))


def register(app: typer.Typer, service_factory) -> None:
    @app.command("fabric-route")
    def fabric_route(
        path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
        mode: SovereigntyMode | None = typer.Option(None, "--mode", help="Override the saved setup policy for this run."),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        """Choose Ypipe, FreeLLMAPI, or OmniRoute from saved policy, canonical constraints, and live health."""
        service: EverstateService = service_factory()
        state = service.status(path)
        effective_mode = mode or SovereigntyMode(configured_policy())

        ypipe_health = _safe_health("ypipe", YpipeFabric)
        free_health = _safe_health("freellmapi", FreeLLMAPIFabric)
        omniroute_health = _safe_health("omniroute", OmniRouteFabric)

        decision = choose_execution_fabric(
            constraints=state.active_constraints,
            mode=effective_mode,
            ypipe_health=ypipe_health,
            freellmapi_health=free_health,
            omniroute_health=omniroute_health,
        )
        report = {
            "project_id": state.project_id,
            "state_version": state.version,
            "mode": effective_mode.value,
            "mode_source": "override" if mode is not None else "setup",
            "constraints": list(state.active_constraints),
            "local_required": decision.local_required,
            "selected": decision.selected,
            "reason": decision.reason,
            "ypipe": {"state": ypipe_health.status, "ready": ypipe_health.ready, "detail": ypipe_health.detail},
            "freellmapi": {"state": free_health.status, "ready": free_health.ready, "detail": free_health.detail},
            "omniroute": {"state": omniroute_health.status, "ready": omniroute_health.ready, "detail": omniroute_health.detail},
        }

        if json_output:
            console.print_json(json.dumps(report))
        else:
            console.print(Panel.fit(
                f"Project: {state.project_id}\nState version: {state.version}\nMode: {effective_mode.value}\n"
                f"Local required: {decision.local_required}\nSelected: {decision.selected or 'NONE'}\nReason: {decision.reason}",
                title="Everstate execution fabric routing",
            ))
        if decision.selected is None:
            raise typer.Exit(code=2)
