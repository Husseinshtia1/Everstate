from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .fabric_routing import SovereigntyMode, choose_execution_fabric
from .freellmapi_fabric import FreeLLMAPIFabric
from .omniroute_fabric import OmniRouteFabric
from .provider_fabric import FabricHealth
from .service import EverstateService
from .ypipe_fabric import YpipeFabric

console = Console()


def _safe_health(factory) -> FabricHealth:
    try:
        return factory().health()
    except (ValueError, OSError, RuntimeError) as exc:
        return FabricHealth(status="UNAVAILABLE", ready=False, detail=str(exc))


def register(app: typer.Typer, service_factory) -> None:
    @app.command("fabric-route")
    def fabric_route(
        path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
        mode: SovereigntyMode = typer.Option(SovereigntyMode.AUTO, "--mode"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        """Choose Ypipe, FreeLLMAPI, or OmniRoute from canonical constraints and live health."""
        service: EverstateService = service_factory()
        state = service.status(path)

        ypipe_health = _safe_health(YpipeFabric)
        free_health = _safe_health(FreeLLMAPIFabric)
        omniroute_health = _safe_health(OmniRouteFabric)

        decision = choose_execution_fabric(
            constraints=state.active_constraints,
            mode=mode,
            ypipe_health=ypipe_health,
            freellmapi_health=free_health,
            omniroute_health=omniroute_health,
        )
        report = {
            "project_id": state.project_id,
            "state_version": state.version,
            "mode": mode.value,
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
            console.print(
                Panel.fit(
                    f"Project: {state.project_id}\n"
                    f"State version: {state.version}\n"
                    f"Mode: {mode.value}\n"
                    f"Local required: {decision.local_required}\n"
                    f"Selected: {decision.selected or 'NONE'}\n"
                    f"Reason: {decision.reason}",
                    title="Everstate execution fabric routing",
                )
            )
        if decision.selected is None:
            raise typer.Exit(code=2)
