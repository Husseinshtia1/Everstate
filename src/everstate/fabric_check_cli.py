from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel

from .provider_readiness import probe_provider
from .providers import get_provider
from .ypipe_fabric import YpipeConfig, YpipeFabric

console = Console()


def register(app: typer.Typer) -> None:
    @app.command("fabric-check")
    def fabric_check(
        json_output: bool = typer.Option(False, "--json"),
        require_both: bool = typer.Option(False, "--require-both"),
        active_omniroute: bool = typer.Option(
            True,
            "--active-omniroute/--passive-omniroute",
            help="Actively query only the OmniRoute gateway/model catalog; never launches Codex.",
        ),
    ) -> None:
        """Check Ypipe and OmniRoute side-by-side without launching any AI worker."""
        try:
            ypipe_config = YpipeConfig.from_env()
            ypipe = YpipeFabric(ypipe_config)
            ypipe_targets = ypipe.discover_targets()
            ypipe_health = ypipe.health()
            ypipe_report = {
                "state": ypipe_health.status,
                "ready": ypipe_health.ready,
                "detail": ypipe_health.detail,
                "base_url": ypipe_config.base_url,
                "models": [target.id for target in ypipe_targets],
                "local_guard": not ypipe_config.allow_remote,
            }
        except (ValueError, OSError) as exc:
            ypipe_report = {
                "state": "UNAVAILABLE",
                "ready": False,
                "detail": str(exc),
                "base_url": None,
                "models": [],
                "local_guard": True,
            }

        provider = get_provider("codex-omniroute")
        omni = probe_provider("codex-omniroute", provider, active=active_omniroute)
        omni_report = {
            "state": omni.state.value,
            "ready": omni.ready,
            "detail": omni.detail,
            "active_check": omni.active_check,
            "selected_model": provider.selected_model(),
        }

        both_ready = bool(ypipe_report["ready"] and omni_report["ready"])
        report = {
            "ypipe": ypipe_report,
            "omniroute": omni_report,
            "both_ready": both_ready,
            "safe_for_dual_fabric_live_test": both_ready,
            "launched_ai_worker": False,
            "canonical_state_mutated": False,
        }

        if json_output:
            console.print_json(json.dumps(report))
        else:
            console.print(
                Panel.fit(
                    f"Ypipe: {ypipe_report['state']} (ready={ypipe_report['ready']})\n"
                    f"OmniRoute: {omni_report['state']} (ready={omni_report['ready']})\n"
                    f"Both ready: {both_ready}\n"
                    "AI worker launched: False\n"
                    "Canonical state mutated: False",
                    title="Everstate execution fabrics",
                )
            )

        if require_both and not both_ready:
            raise typer.Exit(code=2)
