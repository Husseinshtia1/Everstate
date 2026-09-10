from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel

from .ruflo_orchestrator import RufloOrchestrator

console = Console()


def register(app: typer.Typer) -> None:
    @app.command("ruflo-check")
    def ruflo_check(json_output: bool = typer.Option(False, "--json")) -> None:
        """Check whether Ruflo v3 is available for Everstate swarm orchestration."""
        health = RufloOrchestrator().health()
        report = {
            "ready": health.ready,
            "version": health.version,
            "detail": health.detail,
            "authority": "everstate",
            "role": "agent-orchestration",
        }
        if json_output:
            console.print_json(json.dumps(report))
        else:
            console.print(
                Panel.fit(
                    f"Ready: {health.ready}\n"
                    f"Version: {health.version or 'unknown'}\n"
                    f"Detail: {health.detail}\n"
                    "Canonical state authority: Everstate",
                    title="Ruflo orchestration",
                )
            )
        if not health.ready:
            raise typer.Exit(code=2)
