from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .continuation_readiness import assess_continuation_readiness
from .handoff import launch_handoff, prepare_handoff
from .providers import get_provider
from .service import EverstateService
from .work_start import checkpoint_before_provider

console = Console()


def register(app: typer.Typer, service_factory) -> None:
    @app.command("start")
    def start_work(
        task: str = typer.Argument(..., help="The task to persist before opening the target AI."),
        path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
        target: str = typer.Option(
            ...,
            "--target",
            help="Integrated target: claude, codex, gemini, codex-ollama, or codex-omniroute.",
        ),
        objective: str | None = typer.Option(None, "--objective", help="Optional current project objective to persist first."),
        next_action: str | None = typer.Option(None, "--next-action", help="Optional explicit next action; otherwise derived from task + target."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Persist the checkpoint and prepare a handoff without launching the AI."),
    ) -> None:
        """Capture semantic state before any AI provider is contacted, then hand off."""
        service: EverstateService = service_factory()

        # Critical ordering invariant: provider-independent checkpoint first.
        checkpoint = checkpoint_before_provider(
            service,
            root=path,
            task=task,
            target=target,
            objective=objective,
            next_action=next_action,
        )
        readiness = assess_continuation_readiness(service, path)

        console.print(
            Panel.fit(
                f"Project: {checkpoint.project_id}\n"
                f"State version: {checkpoint.state_version}\n"
                f"Task: {checkpoint.task}\n"
                f"Next action: {checkpoint.next_action}\n"
                f"Readiness: {readiness.status}",
                title="Everstate pre-provider checkpoint",
            )
        )

        provider = get_provider(target)
        packet = service.continuation_packet(path)
        if dry_run:
            prepared = prepare_handoff(path, packet, provider)
            console.print(f"[green]Checkpoint persisted before provider launch.[/green]")
            console.print(f"Handoff: {prepared.path}")
            console.print("[dim]Dry run only; no provider process was launched.[/dim]")
            return

        try:
            result = launch_handoff(path, packet, provider)
        except FileNotFoundError as exc:
            # The semantic checkpoint remains safely persisted even when launch fails.
            raise typer.BadParameter(str(exc), param_hint="--target") from exc

        console.print(f"Handoff: {result.path}")
        console.print(f"{provider.name} exited with code {result.returncode}")
        console.print("[dim]The task and next action were persisted before the provider was launched.[/dim]")
