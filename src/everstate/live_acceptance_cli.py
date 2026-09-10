from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .acceptance import ContinuityScenario
from .live_acceptance import StateLevel, run_real_acceptance
from .providers import get_provider
from .service import EverstateService

console = Console()


class CouncilRequirement(StrEnum):
    REQUIRED = "required"
    OFF = "off"


def register(app: typer.Typer, service_factory) -> None:
    @app.command("real-accept")
    def real_accept(
        scenario_path: Path = typer.Option(..., "--scenario", exists=True, dir_okay=False, readable=True),
        template: Path = typer.Option(..., "--template", exists=True, file_okay=False, readable=True),
        workspace: Path = typer.Option(..., "--workspace", file_okay=False),
        provider_name: str = typer.Option(
            "codex",
            "--provider",
            help="Primary coding agent: codex, claude, gemini, codex-ollama, or codex-omniroute.",
        ),
        state_level: StateLevel = typer.Option(StateLevel.FULL, "--state-level"),
        council: CouncilRequirement = typer.Option(CouncilRequirement.REQUIRED, "--council"),
        orchestrator: str = typer.Option(
            "ruflo",
            "--orchestrator",
            help="Council coordinator: ruflo (strict default), auto, or native.",
        ),
        min_council_agents: int = typer.Option(
            2,
            "--min-council-agents",
            min=1,
            max=3,
            help="Minimum independent model participants required before implementation.",
        ),
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            help="Prepare workspace/state and validate prerequisites without launching council models or coding agent.",
        ),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        """Run a real end-to-end build acceptance scenario against a coding agent."""
        service: EverstateService = service_factory()
        scenario = ContinuityScenario.load(scenario_path)
        try:
            provider = get_provider(provider_name)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--provider") from exc
        if not dry_run and not provider.available():
            raise typer.BadParameter(
                f"Primary coding provider {provider_name!r} is not installed or configured.",
                param_hint="--provider",
            )

        try:
            run = run_real_acceptance(
                service=service,
                template=template,
                workspace=workspace,
                scenario=scenario,
                provider=provider,
                state_level=state_level,
                orchestrator=orchestrator,
                require_council=council is CouncilRequirement.REQUIRED,
                min_council_agents=min_council_agents,
                dry_run=dry_run,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            console.print(f"[red]Real acceptance setup/execution failed:[/red] {exc}")
            raise typer.Exit(code=2) from exc

        payload = {
            "workspace": str(run.workspace),
            "artifacts_dir": str(run.artifacts_dir),
            "project_id": run.project_id,
            "initial_state_version": run.initial_state_version,
            "final_state_version": run.final_state_version,
            "state_level": run.state_level.value,
            "council_backend": run.council_backend,
            "council_participants": run.council_participants,
            "provider": run.provider,
            "provider_returncode": run.provider_returncode,
            "report": run.report.model_dump(),
            "dry_run": dry_run,
        }
        if json_output:
            console.print_json(json.dumps(payload))
        else:
            console.print(
                Panel.fit(
                    f"Scenario: {scenario.name}\n"
                    f"Workspace: {run.workspace}\n"
                    f"Project: {run.project_id}@{run.final_state_version}\n"
                    f"State level: {run.state_level.value}\n"
                    f"Council: {run.council_backend} ({run.council_participants} participants)\n"
                    f"Primary agent: {run.provider}\n"
                    f"Evidence: {run.artifacts_dir}\n"
                    f"Acceptance score: {run.report.score:.0%}\n"
                    f"Passed: {run.report.passed}",
                    title="Everstate Real Acceptance",
                )
            )
            for check in run.report.checks:
                mark = "[green]PASS[/green]" if check.passed else "[red]FAIL[/red]"
                console.print(f"{mark} {check.name}: {check.details}")
            if dry_run:
                console.print(
                    "[yellow]Dry run only: council/model execution was not started and the primary coding agent was not contacted.[/yellow]"
                )

        if not dry_run and not run.report.passed:
            raise typer.Exit(code=4)
