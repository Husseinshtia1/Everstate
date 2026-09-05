from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .claude_desktop import (
    associate_claude_desktop_project,
    diagnose_claude_desktop_profiles,
    discover_claude_desktop_projects,
)
from .storage import LocalStore
from .transfer_plan import list_registered_projects

app = typer.Typer(help="Inspect Claude Desktop project sources without reading conversations or secrets.")
console = Console()


@app.callback()
def desktop_cli() -> None:
    return None


def _store() -> LocalStore:
    return LocalStore(Path.home() / ".everstate" / "everstate.db")


@app.command("diagnose")
def diagnose() -> None:
    """Show which Claude Desktop storage surfaces exist without opening sensitive stores."""
    items = diagnose_claude_desktop_profiles()
    table = Table(title="Claude Desktop source diagnosis — structure only")
    table.add_column("Profile root")
    table.add_column("Profile")
    table.add_column("Cowork store")
    table.add_column("spaces.json")
    table.add_column("claude.ai IndexedDB")
    table.add_column("Local Storage")
    table.add_column("Cookies store")
    for item in items:
        table.add_row(
            str(item.profile_root),
            "YES" if item.exists else "NO",
            "YES" if item.local_agent_root_exists else "NO",
            str(item.spaces_file_count),
            "YES" if item.claude_ai_indexeddb_exists else "NO",
            "YES" if item.claude_ai_local_storage_exists else "NO",
            "YES" if item.cookies_store_exists else "NO",
        )
    console.print(table)
    if any(item.has_cloud_renderer_profile for item in items):
        console.print(
            "[cyan]A claude.ai renderer profile exists. The projects visible in Claude Desktop may be cloud Projects rather than local Cowork spaces.[/cyan]"
        )
    if not any(item.has_local_cowork_inventory for item in items):
        console.print("[yellow]No local Cowork spaces.json inventory was detected.[/yellow]")
    console.print(
        "[dim]Diagnosis checks only file/directory existence and counts. It does not open Cookies, IndexedDB, Local Storage, project instructions, or conversations.[/dim]"
    )


@app.command("projects")
def projects(
    json_output: bool = typer.Option(False, "--json", help="Print metadata-only local Cowork inventory as JSON."),
    full_paths: bool = typer.Option(False, "--full-paths", help="Print all local folder assignments without truncation."),
) -> None:
    items = discover_claude_desktop_projects()
    registered = list_registered_projects(_store())
    associations = [associate_claude_desktop_project(item, registered) for item in items]

    if json_output:
        typer.echo(json.dumps([
            {
                "desktop_project_id": a.desktop_project.project_id,
                "name": a.desktop_project.name,
                "folders": [str(path) for path in a.desktop_project.folders],
                "storage_path": str(a.desktop_project.storage_path),
                "account_id": a.desktop_project.account_id,
                "org_id": a.desktop_project.org_id,
                "association": a.status,
                "canonical_project_id": a.project.project_id if a.project else None,
                "canonical_project_name": a.project.name if a.project else None,
                "candidate_project_ids": [item.project_id for item in a.candidates],
                "association_detail": a.detail,
                "metadata_only": True,
                "source_surface": "local-cowork-spaces",
            }
            for a in associations
        ], indent=2))
        return

    table = Table(title="Claude Desktop local Cowork projects — source inventory")
    table.add_column("#")
    table.add_column("Desktop project")
    table.add_column("Desktop ID")
    table.add_column("Folders", justify="right")
    table.add_column("Association")
    table.add_column("Everstate project")
    for index, association in enumerate(associations, start=1):
        item = association.desktop_project
        style = {"VERIFIED": "green", "AMBIGUOUS": "yellow", "UNKNOWN": "red"}[association.status]
        table.add_row(str(index), item.name, item.project_id, str(len(item.folders)), f"[{style}]{association.status}[/{style}]", association.project.name if association.project else "—")
    console.print(table)

    if full_paths:
        console.print("[bold]Claude Desktop local Cowork folder assignments[/bold]")
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
        console.print("[yellow]No local Claude Desktop/Cowork projects were found in spaces.json.[/yellow]")
        console.print("[cyan]This does not prove Claude Desktop has no Projects. claude.ai cloud Projects are a separate source surface.[/cyan]")
    console.print("[dim]Claude Code sessions and the Everstate registry are never substituted into this source inventory.[/dim]")


if __name__ == "__main__":
    app()
