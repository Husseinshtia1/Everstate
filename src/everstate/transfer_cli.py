from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .session_transfer import build_session_transfer_review
from .storage import LocalStore
from .transfer_plan import SourceEnvironment, build_transfer_plan, list_registered_projects

app = typer.Typer(help="Plan an Everstate transfer with explicit source, project scope, and destination.")
console = Console()


def _store() -> LocalStore:
    return LocalStore(Path.home() / ".everstate" / "everstate.db")


@app.command("projects")
def projects() -> None:
    """List projects currently registered in Everstate."""
    items = list_registered_projects(_store())
    table = Table(title="Everstate registered projects")
    table.add_column("Project ID")
    table.add_column("Name")
    table.add_column("Root")
    for project in items:
        table.add_row(project.project_id, project.name, str(project.root_path))
    console.print(table)


@app.callback(invoke_without_command=True)
def transfer_plan(
    source: SourceEnvironment = typer.Option(..., "--from", help="Source AI environment."),
    destination: str = typer.Option(..., "--to", help="Destination AI environment or provider key."),
    project: list[str] = typer.Option([], "--project", help="Project id, name, or root path. Repeat for multiple projects."),
    session: str | None = typer.Option(None, "--session", help="Exact discovered source-session id. Supported for Codex and Claude Code."),
    all_projects: bool = typer.Option(False, "--all", help="Select every registered Everstate project."),
    confirm_all: bool = typer.Option(False, "--confirm-all", help="Required with --all to prevent accidental bulk transfer."),
) -> None:
    """Build and review a transfer plan. This command does not move project state yet."""
    try:
        if session is not None:
            if all_projects:
                raise ValueError("--session cannot be combined with --all")
            if len(project) > 1:
                raise ValueError("A source session can be associated with only one explicit --project")
            review = build_session_transfer_review(
                _store(),
                source=source,
                destination=destination,
                session_id=session,
                project_selector=project[0] if project else None,
            )
            console.print(review.summary())
            console.print(f"Association evidence: {review.association_detail}")
            console.print("[yellow]Review only: no project state or session content was transferred.[/yellow]")
            return

        plan = build_transfer_plan(
            _store(),
            source=source,
            destination=destination,
            project_selectors=project,
            all_projects=all_projects,
            confirm_all=confirm_all,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    console.print(plan.summary())
    console.print("[yellow]Planning only: no project state was transferred.[/yellow]")


if __name__ == "__main__":
    app()
