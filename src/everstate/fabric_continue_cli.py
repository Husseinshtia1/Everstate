from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .execution_fabric_continuation import ExecutionFabricError, execute_fabric_continuation
from .fabric_routing import SovereigntyMode, choose_execution_fabric
from .freellmapi_fabric import FreeLLMAPIError, FreeLLMAPIFabric
from .omniroute_fabric import OmniRouteError, OmniRouteFabric
from .provider_fabric import FabricHealth
from .service import EverstateService
from .ypipe_fabric import YpipeError, YpipeFabric

console = Console()


def _safe_health(fabric) -> FabricHealth:
    try:
        return fabric.health()
    except (ValueError, OSError, YpipeError, FreeLLMAPIError, OmniRouteError) as exc:
        return FabricHealth(status="UNAVAILABLE", ready=False, detail=str(exc))


def register(app: typer.Typer, service_factory) -> None:
    @app.command("fabric-continue")
    def fabric_continue(
        path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
        mode: SovereigntyMode = typer.Option(SovereigntyMode.AUTO, "--mode"),
        model: str | None = typer.Option(None, "--model", help="Optional exact model id on the selected fabric."),
        no_verify_identity: bool = typer.Option(False, "--no-verify-identity", help="Diagnostics only."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Route without sending canonical project state."),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        """Route, execute one verified continuation, and keep Everstate authoritative."""
        service: EverstateService = service_factory()
        packet = service.continuation_packet(path)

        fabrics: dict[str, object | None] = {}
        health: dict[str, FabricHealth] = {}
        for name, factory in (
            ("ypipe", YpipeFabric),
            ("freellmapi", FreeLLMAPIFabric),
            ("omniroute", OmniRouteFabric),
        ):
            try:
                fabric = factory()
                fabrics[name] = fabric
                health[name] = _safe_health(fabric)
            except (ValueError, OSError) as exc:
                fabrics[name] = None
                health[name] = FabricHealth(status="UNAVAILABLE", ready=False, detail=str(exc))

        decision = choose_execution_fabric(
            constraints=packet.constraints,
            mode=mode,
            ypipe_health=health["ypipe"],
            freellmapi_health=health["freellmapi"],
            omniroute_health=health["omniroute"],
        )

        base_report = {
            "project_id": packet.project_id,
            "state_version": packet.state_version,
            "mode": mode.value,
            "constraints": list(packet.constraints),
            "selected": decision.selected,
            "reason": decision.reason,
            "local_required": decision.local_required,
            "ypipe": health["ypipe"].__dict__,
            "freellmapi": health["freellmapi"].__dict__,
            "omniroute": health["omniroute"].__dict__,
            "canonical_state_mutated": False,
        }

        if dry_run:
            base_report["executed"] = False
            if json_output:
                console.print_json(json.dumps(base_report))
            else:
                console.print(Panel.fit(
                    f"Project: {packet.project_id}\nState version: {packet.state_version}\n"
                    f"Selected: {decision.selected or 'NONE'}\nReason: {decision.reason}\nExecuted: False",
                    title="Everstate fabric dry run",
                ))
            if decision.selected is None:
                raise typer.Exit(code=2)
            return

        if decision.selected is None:
            base_report["executed"] = False
            if json_output:
                console.print_json(json.dumps(base_report))
            else:
                console.print(f"[red]No execution fabric is eligible:[/red] {decision.reason}")
            raise typer.Exit(code=2)

        fabric = fabrics.get(decision.selected)
        if fabric is None:
            raise typer.Exit(code=2)

        try:
            result = execute_fabric_continuation(
                fabric,
                packet,
                model=model,
                verify_identity=not no_verify_identity,
            )
        except (ExecutionFabricError, YpipeError, FreeLLMAPIError, OmniRouteError, ValueError) as exc:
            base_report.update({"executed": False, "error": str(exc)})
            if json_output:
                console.print_json(json.dumps(base_report))
            else:
                console.print(f"[red]{decision.selected} continuation failed:[/red] {exc}")
            raise typer.Exit(code=2) from exc

        report = {
            **base_report,
            "executed": True,
            "fabric": result.fabric,
            "target": result.target,
            "verified_identity": result.verified_identity,
            "response": result.response,
        }
        if json_output:
            console.print_json(json.dumps(report))
        else:
            console.print(Panel.fit(
                f"Project: {packet.project_id}\nState version: {packet.state_version}\n"
                f"Fabric: {result.fabric}\nTarget: {result.target}\n"
                f"Identity verified: {result.verified_identity}\nCanonical state mutated: False",
                title="Everstate verified execution continuation",
            ))
            console.print_json(json.dumps(result.response))
