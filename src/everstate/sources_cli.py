from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .source_discovery import AssociationStatus, associate_session, discover_sessions
from .storage import LocalStore
from .transfer_plan import SourceEnvironment, list_registered_projects

app = typer.Typer(help="Discover local AI sessions and associate them with canonical Everstate projects.")
console = Console()


def _store() -> LocalStore:
    return LocalStore(Path.home() / ".everstate" / "everstate.db")


@app.callback(invoke_without_command=True)
def sources_command(
    source: SourceEnvironment = typer.Option(..., "--from", help="Source environment to inspect."),
    limit: int = typer.Option(30, "--limit", min=1, max=500),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    projects = list_registered_projects(_store())
    try:
        sessions = discover_sessions(source)[:limit]
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--from") from exc

    associations = [associate_session(session, projects) for session in sessions]
    if json_output:
        typer.echo(json.dumps([
            {
                "source": item.session.source.value,
                "session_id": item.session.session_id,
                "storage_path": str(item.session.storage_path),
                "working_directory": str(item.session.working_directory) if item.session.working_directory else None,
                "updated_at": item.session.updated_at.isoformat(),
                "association": item.status.value,
                "project_id": item.project.project_id if item.project else None,
                "project_name": item.project.name if item.project else None,
                "candidate_project_ids": [project.project_id for project in item.candidates],
                "detail": item.detail,
                "metadata_only": item.session.metadata_only,
            }
            for item in associations
        ], indent=2))
        return

    table = Table(title=f"Everstate source discovery — {source.value}")
    table.add_column("Session")
    table.add_column("Working directory")
    table.add_column("Association")
    table.add_column("Project")
    table.add_column("Updated")
    for item in associations:
        style = {AssociationStatus.VERIFIED: "green", AssociationStatus.AMBIGUOUS: "yellow", AssociationStatus.UNKNOWN: "red"}[item.status]
        table.add_row(
            item.session.session_id,
            str(item.session.working_directory or "unknown"),
            f"[{style}]{item.status.value}[/{style}]",
            item.project.name if item.project else "—",
            item.session.updated_at.isoformat(timespec="seconds"),
        )
    console.print(table)
    console.print("[dim]Metadata-only discovery: prompt/message bodies are not read or transferred.[/dim]")
    if any(item.status is not AssociationStatus.VERIFIED for item in associations):
        console.print("[yellow]Unverified sessions require explicit user project selection before transfer.[/yellow]")


if __name__ == "__main__":
    app()
