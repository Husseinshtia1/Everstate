from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .project_onboarding import (
    ProjectCandidate,
    ProjectCandidateRole,
    WorkspaceFamily,
    discover_project_candidates,
    discover_workspace_families,
    register_explicit_project_path,
    register_project_candidate,
    register_workspace_family,
)
from .storage import LocalStore
from .transfer_plan import SourceEnvironment, list_registered_projects

app = typer.Typer(help="Discover and register canonical Everstate projects from local AI source metadata.")
console = Console()


def _store() -> LocalStore:
    return LocalStore(Path.home() / ".everstate" / "everstate.db")


def _print_candidates(items: list[ProjectCandidate], *, full_paths: bool = False) -> None:
    table = Table(title="Everstate project onboarding candidates")
    table.add_column("#")
    table.add_column("Project")
    table.add_column("Root")
    table.add_column("Kind")
    table.add_column("Role")
    table.add_column("Sessions", justify="right")
    table.add_column("Sources")
    table.add_column("Status")
    for index, item in enumerate(items, start=1):
        table.add_row(
            str(index),
            item.suggested_name,
            str(item.root_path),
            item.kind.value,
            item.role.value,
            str(item.session_count),
            ", ".join(source.value for source in item.sources),
            "REGISTERED" if item.already_registered else "NEW",
        )
    console.print(table)
    if full_paths:
        console.print("[bold]Full candidate paths[/bold]")
        for index, item in enumerate(items, start=1):
            console.print(f"{index}. {item.root_path} [{item.role.value}]")


def _print_families(items: list[WorkspaceFamily]) -> None:
    if not items:
        console.print("[dim]No safe workspace-family suggestions were found.[/dim]")
        return
    table = Table(title="Suggested workspace families — review only")
    table.add_column("#")
    table.add_column("Family root")
    table.add_column("Role")
    table.add_column("Members", justify="right")
    table.add_column("Sessions", justify="right")
    table.add_column("Sources")
    table.add_column("Status")
    for index, item in enumerate(items, start=1):
        table.add_row(
            str(index),
            str(item.root_path),
            item.role.value,
            str(len(item.members)),
            str(item.session_count),
            ", ".join(source.value for source in item.sources),
            "REGISTERED" if item.already_registered else "SUGGESTED",
        )
    console.print(table)
    for index, item in enumerate(items, start=1):
        console.print(f"[bold]Family {index}: {item.root_path} [{item.role.value}][/bold]")
        for member in item.members:
            console.print(f"  - {member.root_path} [{member.role.value}] ({member.session_count} session(s))")
    console.print(
        "[yellow]Workspace families are suggestions only. A parent root is never registered automatically.[/yellow]"
    )


@app.command("list")
def list_projects() -> None:
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
    full_paths: bool = typer.Option(False, "--full-paths", help="Print every candidate root without table truncation."),
    families: bool = typer.Option(True, "--families/--no-families", help="Show conservative workspace-family suggestions."),
) -> None:
    sources = tuple(source) if source else (SourceEnvironment.CODEX, SourceEnvironment.CLAUDE_CODE)
    store = _store()
    items = discover_project_candidates(store, sources=sources)
    _print_candidates(items, full_paths=full_paths)
    console.print("[dim]Roles are conservative metadata classifications, not proof of project identity. Nothing is registered automatically.[/dim]")
    if families:
        _print_families(discover_workspace_families(store, items))


@app.command("register-path")
def register_path(
    path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    name: str | None = typer.Option(None, "--name", help="Canonical project name. Defaults to the directory name."),
) -> None:
    """Register a project root the user already knows explicitly."""
    root = path.expanduser().resolve()
    console.print("[bold]Explicit canonical project registration[/bold]")
    console.print(f"Root: {root}")
    console.print(f"Name: {name or root.name}")
    console.print("[yellow]This bypasses source-session inference because you are explicitly identifying the project root.[/yellow]")
    if not typer.confirm("Register this exact path as ONE canonical Everstate project?", default=False):
        raise typer.Abort()
    try:
        project = register_explicit_project_path(_store(), root, name)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]Registered canonical project.[/green]")
    console.print(f"- {project.name} [{project.project_id}] {project.root_path}")


@app.command("onboard-family")
def onboard_family(
    source: list[SourceEnvironment] = typer.Option([], "--from", help="Source(s) to inspect. Repeat to combine. Defaults to Codex + Claude Code."),
) -> None:
    sources = tuple(source) if source else (SourceEnvironment.CODEX, SourceEnvironment.CLAUDE_CODE)
    store = _store()
    candidates = discover_project_candidates(store, sources=sources)
    families = discover_workspace_families(store, candidates)
    _print_families(families)
    selectable = [family for family in families if not family.already_registered]
    if not selectable:
        console.print("[green]No unregistered workspace-family suggestions are available.[/green]")
        return

    value = typer.prompt("Family number to register").strip()
    if not value.isdigit() or not 1 <= int(value) <= len(families):
        raise typer.BadParameter("Family number must match the displayed table")
    family = families[int(value) - 1]
    if family.already_registered:
        raise typer.BadParameter("That workspace family is already registered")

    console.print("[bold]Canonical workspace review[/bold]")
    console.print(f"Root to register: {family.root_path}")
    console.print(f"Role: {family.role.value}")
    console.print(f"Member workspaces: {len(family.members)}")
    console.print(f"Observed sessions: {family.session_count}")
    if family.role is ProjectCandidateRole.EXPERIMENT_FAMILY:
        console.print("[red]This looks like an experiment/acceptance family, not a primary project. Prefer register-path for the actual project root.[/red]")
    if not typer.confirm("Use this parent directory as ONE canonical Everstate project?", default=False):
        raise typer.Abort()
    if not typer.confirm("Confirm registration of this workspace-family root", default=False):
        raise typer.Abort()

    project = register_workspace_family(store, family)
    console.print(f"[green]Registered workspace family as one canonical project.[/green]")
    console.print(f"- {project.name} [{project.project_id}] {project.root_path}")


@app.command("onboard")
def onboard(
    source: list[SourceEnvironment] = typer.Option([], "--from", help="Source(s) to inspect. Repeat to combine. Defaults to Codex + Claude Code."),
) -> None:
    sources = tuple(source) if source else (SourceEnvironment.CODEX, SourceEnvironment.CLAUDE_CODE)
    store = _store()
    items = discover_project_candidates(store, sources=sources)
    new_items = [item for item in items if not item.already_registered]
    _print_candidates(items, full_paths=True)
    if not new_items:
        console.print("[green]No unregistered projects were found.[/green]")
        return

    families = discover_workspace_families(store, items)
    risky = [item for item in new_items if item.role in {ProjectCandidateRole.RUN_ARTIFACT, ProjectCandidateRole.EXPERIMENT_FAMILY}]
    if families:
        console.print("[yellow]Workspace-family suggestions exist; review them before registering sibling workspaces separately.[/yellow]")
    if risky:
        console.print("[yellow]Run-artifact candidates are present. Bulk onboarding is disabled.[/yellow]")

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
        if families or risky:
            raise typer.BadParameter("Bulk onboarding is blocked while families or run-artifact candidates require review")
        if not typer.confirm(f"Register ALL {len(new_items)} new projects?", default=False):
            raise typer.Abort()
        selected = new_items
    else:
        raise typer.BadParameter("Choose 1, 2, or 3")

    console.print("[bold]Registration review[/bold]")
    for item in selected:
        console.print(f"- {item.suggested_name}: {item.root_path} [{item.kind.value}/{item.role.value}] ({item.session_count} sessions)")
        if item.role is ProjectCandidateRole.RUN_ARTIFACT:
            console.print("  [red]Warning: this candidate looks like a run artifact rather than a primary project.[/red]")
    if not typer.confirm("Register these canonical projects in Everstate?", default=False):
        raise typer.Abort()

    registered = [register_project_candidate(store, item) for item in selected]
    console.print(f"[green]Registered {len(registered)} project(s).[/green]")
    for project in registered:
        console.print(f"- {project.name} [{project.project_id}] {project.root_path}")


if __name__ == "__main__":
    app()
