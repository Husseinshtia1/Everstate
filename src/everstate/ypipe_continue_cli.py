from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .service import EverstateService
from .ypipe_continuation import execute_ypipe_continuation
from .ypipe_fabric import YpipeConfig, YpipeError, YpipeFabric

console = Console()


def register(app: typer.Typer, service_factory) -> None:
    @app.command("ypipe-continue")
    def ypipe_continue(
        path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
        model: str | None = typer.Option(None, "--model", help="Local model; defaults to EVERSTATE_YPIPE_MODEL or first live model."),
        smartpipe_endpoint: str | None = typer.Option(
            None,
            "--smartpipe-endpoint",
            help="Published Ypipe SmartPipe REST endpoint. Defaults to EVERSTATE_YPIPE_SMARTPIPE_ENDPOINT.",
        ),
        no_verify_identity: bool = typer.Option(
            False,
            "--no-verify-identity",
            help="Permit an unverified Ypipe response. Intended only for diagnostics.",
        ),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        """Continue current verified Everstate state through local Ypipe without mutating canonical state."""
        service: EverstateService = service_factory()
        packet = service.continuation_packet(path)
        config = YpipeConfig.from_env()
        fabric = YpipeFabric(config)
        endpoint = smartpipe_endpoint or config.smartpipe_endpoint
        try:
            result = execute_ypipe_continuation(
                fabric,
                packet,
                model=model or config.model,
                smartpipe_endpoint=endpoint,
                verify_identity=not no_verify_identity,
            )
        except YpipeError as exc:
            if json_output:
                console.print_json(
                    json.dumps(
                        {
                            "ready": False,
                            "error": str(exc),
                            "project_id": packet.project_id,
                            "state_version": packet.state_version,
                        }
                    )
                )
            else:
                console.print(f"[red]Ypipe continuation failed:[/red] {exc}")
            raise typer.Exit(code=2) from exc

        report = {
            "ready": True,
            "project_id": packet.project_id,
            "state_version": packet.state_version,
            "mode": result.mode,
            "target": result.target,
            "verified_identity": result.verified_identity,
            "response": result.response,
            "canonical_state_mutated": False,
        }
        if json_output:
            console.print_json(json.dumps(report))
        else:
            console.print(
                Panel.fit(
                    f"Project: {packet.project_id}\n"
                    f"State version: {packet.state_version}\n"
                    f"Mode: {result.mode}\n"
                    f"Target: {result.target}\n"
                    f"Identity verified: {result.verified_identity}\n"
                    "Canonical state mutated: False",
                    title="Everstate Ypipe continuation",
                )
            )
            console.print_json(json.dumps(result.response))
