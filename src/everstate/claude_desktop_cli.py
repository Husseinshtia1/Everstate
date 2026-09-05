from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .claude_desktop import associate_claude_desktop_project, discover_claude_desktop_projects
from .storage import LocalStore
from .transfer_plan import list_registered_projects

app = typer.Typer(help="Inspect Claude Desktop/Cowork local project metadata only.")
console = Console()


@app.callback()
def desktop_cli() -> None:
    """Inspect Claude Desktop/Cowork local project metadata only."""
    return None


def _store() -> LocalStore:
    return LocalStore(Path.home() / ".everstate" / "everstate.db")


@app.command("projects")
def projects(
    json_output: bool = typer.Option(False, "--json", help="Print metadata-only inventory as JSON."),
    full_paths: bool = typer.Option(False, "--full-paths", help="Print all local folder assignments without truncation."),
) -> None:
    """List actual local Claude Desktop/Cowork projects from Desktop storage."""
    items = discover_claude_desktop_projects()
    registered = list_registered_projects(_store())
    associations = [associate_claude_desktop_project(item, registered) for item in items]

    if json_output:
        typer.echo(
            json.dumps(
                [
                    {
                        "desktop_project_id": association.desktop_project.project_id,
                        "name": association.desktop_project.name,
                        "folders": [str(path) for path in association.desktop_project.folders],
                        "storage_path": str(association.desktop_project.storage_path),
                        "account_id": association.desktop_project.account_id,
                        "org_id": association.desktop_project.org_id,
                        "association": association.status,
                        "canonical_project_id": association.project.project_id if association.project else None,
                        "canonical_project_name": association.project.name if association.project else None,
                        "candidate_project_ids": [item.project_id for item in association.candidates],
                        "association_detail": association.detail,
                        "metadata_only": True,
                    }
                    for association in associations
                ],
                indent=2,
            )
        )
        return

    table = Table(title="Claude Desktop local projects — source inventory")
    table.add_column("#")
    table.add_column("Desktop project")
    table.add_column("Desktop ID")
    table.add_column("Folders", justify="right")
    table.add_column("Association")
    table.add_column("Everstate project")
    for index, association in enumerate(associations, start=1):
        item = association.desktop_project
        style = {"VERIFIED": "green", "AMBIGUOUS": "yellow", "UNKNOWN": "red"}[association.status]
        table.add_row(
            str(index),
            item.name,
            item.project_id,
            str(len(item.folders)),
            f"[{style}]{association.status}[/{style}]",
            association.project.name if association.project else "—",
        )
    console.print(table)

    if full_paths:
        console.print("[bold]Claude Desktop folder assignments[/bold]")
        for index, association in enumerate(associations, start=1):
            item = association.desktop_project
            console.print(f"{index}. {item.name} [{item.project_id}]")
            if item.folders:
                for folder in item.folders:
                    console.print(f"   - {folder}")
            else:
                console.print("   - [dim]No local folder exposed by Desktop metadata[/dim]")
            console.print(f"   Association: {association.status} — {association.detail}")

    if not items:
        console.print(
            "[yellow]No local Claude Desktop/Cowork projects were found in the supported Desktop metadata store.[/yellow]"
        )
    console.print(
        "[dim]Source inventory comes only from Claude Desktop/Cowork spaces.json metadata. "
        "Claude Code sessions and the Everstate registry are not substituted into this list.[/dim]"
    )


if __name__ == "__main__":
    app()
