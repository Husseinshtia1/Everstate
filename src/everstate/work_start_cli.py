from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .continuation_readiness import assess_continuation_readiness
from .execution_config import configured_policy, fabric_enabled
from .execution_fabric_continuation import ExecutionFabricError, execute_fabric_continuation
from .fabric_routing import SovereigntyMode, choose_execution_fabric
from .freellmapi_fabric import FreeLLMAPIError, FreeLLMAPIFabric
from .handoff import launch_handoff, prepare_handoff
from .omniroute_fabric import OmniRouteError, OmniRouteFabric
from .provider_fabric import FabricHealth
from .providers import get_provider
from .service import EverstateService
from .work_start import checkpoint_before_provider
from .ypipe_continuation import execute_ypipe_continuation, write_ypipe_handoff
from .ypipe_fabric import YpipeConfig, YpipeError, YpipeFabric

console = Console()


def _safe_fabric(name: str, factory):
    if not fabric_enabled(name):
        return None, FabricHealth("DISABLED", False, "Disabled by Everstate setup policy.")
    try:
        fabric = factory()
        return fabric, fabric.health()
    except (ValueError, OSError, RuntimeError) as exc:
        return None, FabricHealth("UNAVAILABLE", False, str(exc))


def register(app: typer.Typer, service_factory) -> None:
    @app.command("start")
    def start_work(
        task: str = typer.Argument(..., help="The task to persist before execution."),
        path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
        target: str = typer.Option(
            "auto",
            "--target",
            help="Default: auto. Or choose claude, codex, gemini, codex-ollama, codex-omniroute, or ypipe.",
        ),
        objective: str | None = typer.Option(None, "--objective", help="Optional current project objective to persist first."),
        next_action: str | None = typer.Option(None, "--next-action", help="Optional explicit next action."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Persist checkpoint and route/prepare without contacting AI."),
    ) -> None:
        """Checkpoint first; by default route automatically using the saved setup policy."""
        service: EverstateService = service_factory()

        checkpoint = checkpoint_before_provider(
            service,
            root=path,
            task=task,
            target=target,
            objective=objective,
            next_action=next_action,
        )
        readiness = assess_continuation_readiness(service, path)

        console.print(Panel.fit(
            f"Project: {checkpoint.project_id}\nState version: {checkpoint.state_version}\n"
            f"Task: {checkpoint.task}\nNext action: {checkpoint.next_action}\nReadiness: {readiness.status}",
            title="Everstate pre-provider checkpoint",
        ))

        packet = service.continuation_packet(path)

        if target == "auto":
            fabrics: dict[str, object | None] = {}
            health: dict[str, FabricHealth] = {}
            for name, factory in (
                ("ypipe", YpipeFabric),
                ("freellmapi", FreeLLMAPIFabric),
                ("omniroute", OmniRouteFabric),
            ):
                fabric, state = _safe_fabric(name, factory)
                fabrics[name] = fabric
                health[name] = state

            mode = SovereigntyMode(configured_policy())
            decision = choose_execution_fabric(
                constraints=packet.constraints,
                mode=mode,
                ypipe_health=health["ypipe"],
                freellmapi_health=health["freellmapi"],
                omniroute_health=health["omniroute"],
            )
            console.print(f"Automatic route: [cyan]{decision.selected or 'NONE'}[/cyan] — {decision.reason}")
            if decision.selected is None:
                console.print("[red]No eligible execution fabric is ready. The checkpoint remains safely persisted.[/red]")
                raise typer.Exit(code=2)
            if dry_run:
                console.print("[green]Checkpoint persisted and automatic route validated; no AI was contacted.[/green]")
                return
            fabric = fabrics[decision.selected]
            if fabric is None:
                raise typer.Exit(code=2)
            try:
                result = execute_fabric_continuation(fabric, packet, verify_identity=True)
            except (ExecutionFabricError, YpipeError, FreeLLMAPIError, OmniRouteError, ValueError) as exc:
                console.print(f"[red]Automatic continuation failed:[/red] {exc}")
                console.print("[dim]The semantic checkpoint remains persisted despite execution failure.[/dim]")
                raise typer.Exit(code=2) from exc
            console.print(
                f"Continuation succeeded via [cyan]{result.fabric}[/cyan] target {result.target}; "
                f"identity verified: {result.verified_identity}"
            )
            console.print_json(json.dumps(result.response))
            console.print("[dim]Canonical Everstate state was not mutated by the execution response.[/dim]")
            return

        if target == "ypipe":
            config = YpipeConfig.from_env()
            handoff_path = write_ypipe_handoff(path, packet)
            if dry_run:
                console.print("[green]Checkpoint and Ypipe handoff persisted before any Ypipe contact.[/green]")
                console.print(f"Handoff: {handoff_path}")
                console.print("[dim]Dry run only; Ypipe was not contacted.[/dim]")
                return
            try:
                fabric = YpipeFabric(config)
                result = execute_ypipe_continuation(
                    fabric,
                    packet,
                    model=config.model,
                    smartpipe_endpoint=config.smartpipe_endpoint,
                    verify_identity=True,
                )
            except (YpipeError, ValueError) as exc:
                console.print(f"Handoff: {handoff_path}")
                console.print(f"[red]Ypipe continuation failed:[/red] {exc}")
                raise typer.Exit(code=2) from exc
            console.print(f"Handoff: {handoff_path}")
            console.print(f"Ypipe continuation succeeded via {result.mode} target {result.target}; identity verified: {result.verified_identity}")
            console.print_json(json.dumps(result.response))
            console.print("[dim]Canonical Everstate state was not mutated by the Ypipe response.[/dim]")
            return

        provider = get_provider(target)
        if dry_run:
            prepared = prepare_handoff(path, packet, provider)
            console.print("[green]Checkpoint persisted before provider launch.[/green]")
            console.print(f"Handoff: {prepared.path}")
            console.print("[dim]Dry run only; no provider process was launched.[/dim]")
            return

        try:
            result = launch_handoff(path, packet, provider)
        except FileNotFoundError as exc:
            raise typer.BadParameter(str(exc), param_hint="--target") from exc

        console.print(f"Handoff: {result.path}")
        console.print(f"{provider.name} exited with code {result.returncode}")
        console.print("[dim]The task and next action were persisted before the provider was launched.[/dim]")
