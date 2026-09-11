from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .phased_autobuild import AutobuildPlan, run_phased_autobuild
from .providers import get_provider

console = Console()


def register(app: typer.Typer, service_factory) -> None:
    @app.command("autobuild")
    def autobuild(
        plan_path: Path = typer.Option(..., "--plan", exists=True, dir_okay=False, readable=True),
        template: Path = typer.Option(..., "--template", exists=True, file_okay=False, readable=True),
        workspace: Path = typer.Option(..., "--workspace", file_okay=False),
        provider_name: str = typer.Option("codex", "--provider"),
        orchestrator: str = typer.Option("ruflo", "--orchestrator"),
        min_council_agents: int = typer.Option(2, "--min-council-agents", min=1, max=3),
        dry_run: bool = typer.Option(False, "--dry-run"),
        resume: bool = typer.Option(False, "--resume", help="Resume and revalidate an existing phased autobuild workspace."),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        """Execute or safely resume a multi-stage autonomous build with deterministic gates."""
        plan = AutobuildPlan.load(plan_path)
        try:
            provider = get_provider(provider_name)
            run = run_phased_autobuild(
                service=service_factory(),
                template=template,
                workspace=workspace,
                plan=plan,
                provider=provider,
                orchestrator=orchestrator,
                min_council_agents=min_council_agents,
                dry_run=dry_run,
                resume=resume,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            console.print(f"[red]Autobuild failed:[/red] {exc}")
            raise typer.Exit(code=2) from exc

        payload = {
            "workspace": str(run.workspace),
            "artifacts_dir": str(run.artifacts_dir),
            "project_id": run.project_id,
            "provider": run.provider,
            "passed": run.passed,
            "dry_run": dry_run,
            "resume": resume,
            "stages": [
                {
                    "id": stage.stage_id,
                    "title": stage.title,
                    "passed": stage.passed,
                    "attempts": stage.attempt_count,
                    "council_backend": stage.council_backend,
                    "council_participants": stage.council_participants,
                }
                for stage in run.stages
            ],
        }
        if json_output:
            console.print_json(json.dumps(payload))
        else:
            console.print(Panel.fit(
                f"Plan: {plan.name}\nWorkspace: {run.workspace}\nProject: {run.project_id}\n"
                f"Provider: {run.provider}\nStages: {len(run.stages)}/{len(plan.stages)}\n"
                f"Resume: {resume}\nPassed: {run.passed}",
                title="Everstate Phased Autobuild",
            ))
            for stage in run.stages:
                mark = "[green]PASS[/green]" if stage.passed else "[red]FAIL[/red]"
                console.print(f"{mark} {stage.stage_id} {stage.title} attempts={stage.attempt_count} council={stage.council_backend}/{stage.council_participants}")

        if not dry_run and not run.passed:
            raise typer.Exit(code=4)
