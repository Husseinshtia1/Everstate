from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel

from .execution_config import fabric_enabled
from .freellmapi_fabric import FreeLLMAPIFabric
from .provider_readiness import probe_provider
from .providers import get_provider
from .ypipe_fabric import YpipeConfig, YpipeFabric

console = Console()


def register(app: typer.Typer) -> None:
    @app.command("fabric-check")
    def fabric_check(
        json_output: bool = typer.Option(False, "--json"),
        require_all: bool = typer.Option(False, "--require-all", help="Require every enabled fabric to be ready."),
        active_omniroute: bool = typer.Option(True, "--active-omniroute/--passive-omniroute"),
    ) -> None:
        """Check Ypipe, FreeLLMAPI, and OmniRoute without launching any AI worker."""
        if fabric_enabled("ypipe"):
            try:
                config = YpipeConfig.from_env()
                ypipe = YpipeFabric(config)
                targets = ypipe.discover_targets()
                h = ypipe.health()
                ypipe_report = {"state": h.status, "ready": h.ready, "detail": h.detail, "models": [t.id for t in targets]}
            except (ValueError, OSError, RuntimeError) as exc:
                ypipe_report = {"state": "UNAVAILABLE", "ready": False, "detail": str(exc), "models": []}
        else:
            ypipe_report = {"state": "DISABLED", "ready": False, "detail": "Disabled by setup policy.", "models": []}

        if fabric_enabled("freellmapi"):
            try:
                free = FreeLLMAPIFabric()
                targets = free.discover_targets()
                h = free.health()
                free_report = {"state": h.status, "ready": h.ready, "detail": h.detail, "models": [t.id for t in targets]}
            except (ValueError, OSError, RuntimeError) as exc:
                free_report = {"state": "UNAVAILABLE", "ready": False, "detail": str(exc), "models": []}
        else:
            free_report = {"state": "DISABLED", "ready": False, "detail": "Disabled by setup policy.", "models": []}

        if fabric_enabled("omniroute"):
            provider = get_provider("codex-omniroute")
            omni = probe_provider("codex-omniroute", provider, active=active_omniroute)
            omni_report = {
                "state": omni.state.value,
                "ready": omni.ready,
                "detail": omni.detail,
                "active_check": omni.active_check,
                "selected_model": provider.selected_model(),
            }
        else:
            omni_report = {"state": "DISABLED", "ready": False, "detail": "Disabled by setup policy.", "active_check": False, "selected_model": None}

        reports = {"ypipe": ypipe_report, "freellmapi": free_report, "omniroute": omni_report}
        enabled = [name for name in reports if fabric_enabled(name)]
        all_enabled_ready = bool(enabled) and all(reports[name]["ready"] for name in enabled)
        any_ready = any(report["ready"] for report in reports.values())
        report = {
            **reports,
            "enabled_fabrics": enabled,
            "any_ready": any_ready,
            "all_enabled_ready": all_enabled_ready,
            "safe_for_live_test": any_ready,
            "launched_ai_worker": False,
            "canonical_state_mutated": False,
        }

        if json_output:
            console.print_json(json.dumps(report))
        else:
            console.print(Panel.fit(
                f"Ypipe: {ypipe_report['state']} (ready={ypipe_report['ready']})\n"
                f"FreeLLMAPI: {free_report['state']} (ready={free_report['ready']})\n"
                f"OmniRoute: {omni_report['state']} (ready={omni_report['ready']})\n"
                f"Any ready: {any_ready}\nAll enabled ready: {all_enabled_ready}\n"
                "AI worker launched: False\nCanonical state mutated: False",
                title="Everstate execution fabrics",
            ))

        if require_all and not all_enabled_ready:
            raise typer.Exit(code=2)
        if not any_ready:
            raise typer.Exit(code=2)
