from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .execution_fabric_continuation import ExecutionFabricError, execute_fabric_continuation
from .fabric_routing import SovereigntyMode, choose_execution_fabric
from .omniroute_fabric import OmniRouteError, OmniRouteFabric
from .provider_fabric import FabricHealth
from .service import EverstateService
from .ypipe_fabric import YpipeError, YpipeFabric

console = Console()


def _safe_health(fabric) -> FabricHealth:
    try:
        return fabric.health()
    except (ValueError, OSError, YpipeError, OmniRouteError) as exc:
        return FabricHealth(status="UNAVAILABLE", ready=False, detail=str(exc))


def register(app: typer.Typer, service_factory) -> None:
    @app.command("fabric-continue")
    def fabric_continue(
        path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
        mode: SovereigntyMode = typer.Option(SovereigntyMode.AUTO, "--mode"),
        model: str | None = typer.Option(
            None,
            "--model",
            help="Optional exact model id on the selected fabric. Defaults to the first live target.",
        ),
        no_verify_identity: bool = typer.Option(
            False,
            "--no-verify-identity",
            help="Allow a response that does not echo the exact Everstate project/state identity. Diagnostics only.",
        ),
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            help="Route and report health without sending canonical project state to any execution fabric.",
        ),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        """Route to Ypipe or OmniRoute, execute one verified continuation, and keep Everstate authoritative."""
        service: EverstateService = service_factory()
        packet = service.continuation_packet(path)

        try:
            ypipe = YpipeFabric()
            ypipe_health = _safe_health(ypipe)
        except (ValueError, OSError) as exc:
            ypipe = None
            ypipe_health = FabricHealth(status="UNAVAILABLE", ready=False, detail=str(exc))

        try:
            omniroute = OmniRouteFabric()
            omniroute_health = _safe_health(omniroute)
        except (ValueError, OSError) as exc:
            omniroute = None
            omniroute_health = FabricHealth(status="UNAVAILABLE", ready=False, detail=str(exc))

        decision = choose_execution_fabric(
            constraints=packet.constraints,
            mode=mode,
            ypipe_health=ypipe_health,
            omniroute_health=omniroute_health,
        )

        base_report = {
            "project_id": packet.project_id,
            "state_version": packet.state_version,
            "mode": mode.value,
            "constraints": list(packet.constraints),
            "selected": decision.selected,
            "reason": decision.reason,
            "local_required": decision.local_required,
            "ypipe": {
                "state": ypipe_health.status,
                "ready": ypipe_health.ready,
                "detail": ypipe_health.detail,
            },
            "omniroute": {
                "state": omniroute_health.status,
                "ready": omniroute_health.ready,
                "detail": omniroute_health.detail,
            },
            "canonical_state_mutated": False,
        }

        if dry_run:
            base_report["executed"] = False
            if json_output:
                console.print_json(json.dumps(base_report))
            else:
                console.print(
                    Panel.fit(
                        f"Project: {packet.project_id}\n"
                        f"State version: {packet.state_version}\n"
                        f"Selected: {decision.selected or 'NONE'}\n"
                        f"Reason: {decision.reason}\n"
                        "Executed: False",
                        title="Everstate dual-fabric dry run",
                    )
                )
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

        fabric = ypipe if decision.selected == "ypipe" else omniroute
        if fabric is None:
            console.print(f"[red]Selected fabric {decision.selected} could not be initialized.[/red]")
            raise typer.Exit(code=2)

        try:
            result = execute_fabric_continuation(
                fabric,
                packet,
                model=model,
                verify_identity=not no_verify_identity,
            )
        except (ExecutionFabricError, YpipeError, OmniRouteError, ValueError) as exc:
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
            console.print(
                Panel.fit(
                    f"Project: {packet.project_id}\n"
                    f"State version: {packet.state_version}\n"
                    f"Fabric: {result.fabric}\n"
                    f"Target: {result.target}\n"
                    f"Identity verified: {result.verified_identity}\n"
                    "Canonical state mutated: False",
                    title="Everstate verified execution continuation",
                )
            )
            console.print_json(json.dumps(result.response))
