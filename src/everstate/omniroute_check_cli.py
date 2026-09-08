from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel

from .provider_readiness import probe_provider
from .providers import get_provider

console = Console()


def register(app: typer.Typer) -> None:
    @app.command("omniroute-check")
    def omniroute_check(
        active: bool = typer.Option(
            False,
            "--active",
            help="Actively query only the configured OmniRoute gateway/model catalog.",
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            help="Emit a machine-readable acceptance report.",
        ),
    ) -> None:
        """Check only the OmniRoute-backed Codex path without probing other providers."""
        provider = get_provider("codex-omniroute")
        result = probe_provider("codex-omniroute", provider, active=active)
        report = {
            "key": result.key,
            "name": result.name,
            "state": result.state.value,
            "ready": result.ready,
            "detail": result.detail,
            "executable": result.executable,
            "active_check": result.active_check,
            "selected_model": provider.selected_model(),
            "command_preview": provider.interactive_command("EVERSTATE_OMNIROUTE_PREFLIGHT"),
        }

        if json_output:
            console.print_json(json.dumps(report))
        else:
            console.print(
                Panel.fit(
                    f"State: {report['state']}\n"
                    f"Ready: {report['ready']}\n"
                    f"Active check: {report['active_check']}\n"
                    f"Selected model: {report['selected_model'] or 'OmniRoute default'}\n"
                    f"Detail: {report['detail']}",
                    title="Everstate OmniRoute check",
                )
            )

        if not result.ready:
            raise typer.Exit(code=2)
