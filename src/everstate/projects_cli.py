from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .project_onboarding import ProjectCandidate, discover_project_candidates, register_project_candidate
from .storage import LocalStore
from .transfer_plan import SourceEnvironment, list_registered_projects

app = typer.Typer(help="Discover and register canonical Everstate projects from local AI source metadata.")
console = Console()


def _store() -> LocalStore:
    return LocalStore(Path.home() / ".everstate" / "everstate.db")


def _print_candidates(items: list[ProjectCandidate]) -> None:
    table = Table(title="Everstate project onboarding candidates")
    table.add_column("#")
    table.add_column("Project")
    table.add_column("Root")
    table.add_column("Sessions", justify="right")
    table.add_column("Sources")
    table.add_column("Status")
    for index, item in enumerate(items, start=1):
        table.add_row(
            str(index),
            item.suggested_name,
            str(item.root_path),
            str(item.session_count),
            ", ".join(source.value for source in item.sources),
            "REGISTERED" if item.already_registered else "NEW",
        )
    console.print(table)


@app.command("list")
def list_projects() -> None:
    """List canonical projects already registered in Everstate."""
    table = Table(title="Everstate registered projects")
    table.add_column("Project ID")
    table.add_column("Name")
    table.add_column("Root")
    for project in list_registered_projects(_store()):
        table.add_row(project.project_id, project.name, str(project.root_path))
    console.print(table)


@app.command("discover")
def discover(
    source: list[SourceEnvironment] = typer.Option([], "--from", help="Source(s) to inspect. Repeat to combine. Defaults to Codex + Claude Code."),
) -> None:
    """Show unique Git projects inferred from source-session working directories."""
    sources = tuple(source) if source else (SourceEnvironment.CODEX, SourceEnvironment.CLAUDE_CODE)
    items = discover_project_candidates(_store(), sources=sources)
    _print_candidates(items)
    console.print("[dim]Only existing local Git repositories are proposed. Nothing is registered automatically.[/dim]")


@app.command("onboard")
def onboard(
    source: list[SourceEnvironment] = typer.Option([], "--from", help="Source(s) to inspect. Repeat to combine. Defaults to Codex + Claude Code."),
) -> None:
    """Interactively register one, selected, or all discovered Git projects."""
    sources = tuple(source) if source else (SourceEnvironment.CODEX, SourceEnvironment.CLAUDE_CODE)
    items = discover_project_candidates(_store(), sources=sources)
    new_items = [item for item in items if not item.already_registered]
    _print_candidates(items)
    if not new_items:
        console.print("[green]No unregistered Git projects were found.[/green]")
        return

    console.print("[bold]What do you want to register?[/bold]")
    console.print("  1. One project")
    console.print("  2. Selected projects")
    console.print("  3. All NEW projects")
    choice = typer.prompt("Selection", default="1").strip()

    selected: list[ProjectCandidate]
    if choice == "1":
        value = typer.prompt("Candidate number").strip()
        if not value.isdigit() or not 1 <= int(value) <= len(items):
            raise typer.BadParameter("Candidate number must match the displayed table")
        candidate = items[int(value) - 1]
        if candidate.already_registered:
            raise typer.BadParameter("That project is already registered")
        selected = [candidate]
    elif choice == "2":
        raw = typer.prompt("Candidate numbers, comma separated").strip()
        numbers = [part.strip() for part in raw.split(",") if part.strip()]
        selected = []
        seen: set[Path] = set()
        for value in numbers:
            if not value.isdigit() or not 1 <= int(value) <= len(items):
                raise typer.BadParameter("Every candidate number must match the displayed table")
            candidate = items[int(value) - 1]
            if candidate.already_registered:
                continue
            if candidate.root_path not in seen:
                selected.append(candidate)
                seen.add(candidate.root_path)
        if not selected:
            raise typer.BadParameter("No new projects were selected")
    elif choice == "3":
        if not typer.confirm(f"Register ALL {len(new_items)} new projects?", default=False):
            raise typer.Abort()
        selected = new_items
    else:
        raise typer.BadParameter("Choose 1, 2, or 3")

    console.print("[bold]Registration review[/bold]")
    for item in selected:
        console.print(f"- {item.suggested_name}: {item.root_path} ({item.session_count} discovered sessions)")
    if not typer.confirm("Register these canonical projects in Everstate?", default=False):
        raise typer.Abort()

    registered = [register_project_candidate(_store(), item) for item in selected]
    console.print(f"[green]Registered {len(registered)} project(s).[/green]")
    for project in registered:
        console.print(f"- {project.name} [{project.project_id}] {project.root_path}")


if __name__ == "__main__":
    app()
