from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .session_transfer import build_session_transfer_review
from .source_discovery import AssociationStatus, associate_session, discover_sessions
from .storage import LocalStore
from .transfer_plan import SourceEnvironment, build_transfer_plan, list_registered_projects

app = typer.Typer(help="Plan an Everstate transfer with explicit source, project scope, and destination.")
console = Console()


def _store() -> LocalStore:
    return LocalStore(Path.home() / ".everstate" / "everstate.db")


def _parse_source(value: str) -> SourceEnvironment:
    try:
        return SourceEnvironment(value.strip())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in SourceEnvironment)
        raise ValueError(f"Unknown source environment {value!r}. Choose one of: {allowed}") from exc


def _prompt_source() -> SourceEnvironment:
    choices = list(SourceEnvironment)
    console.print("[bold]Where are you continuing from?[/bold]")
    for index, item in enumerate(choices, start=1):
        console.print(f"  {index}. {item.value}")
    while True:
        value = typer.prompt("Source number").strip()
        if value.isdigit() and 1 <= int(value) <= len(choices):
            return choices[int(value) - 1]
        console.print("[yellow]Choose one of the listed source numbers.[/yellow]")


def _prompt_destination() -> str:
    choices = [
        ("auto", "Best available continuation target"),
        ("claude", "Claude Code"),
        ("codex", "Codex"),
        ("gemini", "Gemini CLI"),
        ("codex-ollama", "Local Codex + Ollama"),
        ("manual", "Portable/manual handoff"),
        ("custom", "Enter another destination key"),
    ]
    console.print("[bold]Where do you want to continue?[/bold]")
    for index, (key, label) in enumerate(choices, start=1):
        console.print(f"  {index}. {label} ({key})")
    while True:
        value = typer.prompt("Destination number", default="1").strip()
        if value.isdigit() and 1 <= int(value) <= len(choices):
            key = choices[int(value) - 1][0]
            if key == "custom":
                custom = typer.prompt("Destination key").strip()
                if custom:
                    return custom
                continue
            return key
        console.print("[yellow]Choose one of the listed destination numbers.[/yellow]")


def _print_project_table(items) -> None:
    table = Table(title="Everstate registered projects")
    table.add_column("#")
    table.add_column("Project ID")
    table.add_column("Name")
    table.add_column("Root")
    for index, project in enumerate(items, start=1):
        table.add_row(str(index), project.project_id, project.name, str(project.root_path))
    console.print(table)


def _selector_from_number(value: str, items) -> str:
    if not value.isdigit() or not 1 <= int(value) <= len(items):
        raise ValueError("Project selection must be one of the displayed numbers")
    return items[int(value) - 1].project_id


def _prompt_project_selection(store: LocalStore, *, allow_many: bool = True) -> tuple[list[str], bool, bool]:
    items = list_registered_projects(store)
    if not items:
        raise ValueError("No projects are registered in Everstate")
    _print_project_table(items)

    console.print("[bold]Which project scope do you want?[/bold]")
    console.print("  1. One project")
    if allow_many:
        console.print("  2. Selected projects")
        console.print("  3. All projects")
    choice = typer.prompt("Scope number", default="1").strip()

    if choice == "1":
        selector = _selector_from_number(typer.prompt("Project number").strip(), items)
        return [selector], False, False

    if allow_many and choice == "2":
        raw = typer.prompt("Project numbers, comma separated").strip()
        values = [part.strip() for part in raw.split(",") if part.strip()]
        if not values:
            raise ValueError("Select at least one project")
        selectors: list[str] = []
        for value in values:
            selector = _selector_from_number(value, items)
            if selector not in selectors:
                selectors.append(selector)
        return selectors, False, False

    if allow_many and choice == "3":
        confirmed = typer.confirm(
            f"You selected ALL {len(items)} registered projects. Continue with all projects?",
            default=False,
        )
        if not confirmed:
            raise ValueError("Bulk transfer selection cancelled")
        return [], True, True

    raise ValueError("Unknown project scope selection")


def _prompt_session_or_projects(store: LocalStore, source: SourceEnvironment) -> tuple[str | None, list[str], bool, bool]:
    if source not in {SourceEnvironment.CODEX, SourceEnvironment.CLAUDE_CODE}:
        projects, all_projects, confirm_all = _prompt_project_selection(store)
        return None, projects, all_projects, confirm_all

    try:
        sessions = discover_sessions(source)[:20]
    except ValueError:
        sessions = []
    if not sessions:
        projects, all_projects, confirm_all = _prompt_project_selection(store)
        return None, projects, all_projects, confirm_all

    projects = list_registered_projects(store)
    associations = [associate_session(session, projects) for session in sessions]
    table = Table(title=f"Recent {source.value} sessions")
    table.add_column("#")
    table.add_column("Session")
    table.add_column("Workdir")
    table.add_column("Association")
    table.add_column("Project")
    for index, item in enumerate(associations, start=1):
        table.add_row(
            str(index),
            item.session.session_id,
            str(item.session.working_directory or "unknown"),
            item.status.value,
            item.project.name if item.project else "—",
        )
    console.print(table)

    if not typer.confirm("Choose a specific discovered source session?", default=True):
        selected, all_projects, confirm_all = _prompt_project_selection(store)
        return None, selected, all_projects, confirm_all

    value = typer.prompt("Session number").strip()
    if not value.isdigit() or not 1 <= int(value) <= len(associations):
        raise ValueError("Session selection must be one of the displayed numbers")
    association = associations[int(value) - 1]
    session_id = association.session.session_id

    if association.status is AssociationStatus.VERIFIED:
        return session_id, [], False, False

    console.print(
        f"[yellow]Session association is {association.status.value}; choose its project explicitly before continuing.[/yellow]"
    )
    selected, _, _ = _prompt_project_selection(store, allow_many=False)
    return session_id, selected, False, False


@app.command("projects")
def projects() -> None:
    """List projects currently registered in Everstate."""
    _print_project_table(list_registered_projects(_store()))


@app.callback(invoke_without_command=True)
def transfer_plan(
    source: str | None = typer.Option(None, "--from", help="Source AI environment."),
    destination: str | None = typer.Option(None, "--to", help="Destination AI environment or provider key."),
    project: list[str] = typer.Option([], "--project", help="Project id, name, or root path. Repeat for multiple projects."),
    session: str | None = typer.Option(None, "--session", help="Exact discovered source-session id. Supported for Codex and Claude Code."),
    all_projects: bool = typer.Option(False, "--all", help="Select every registered Everstate project."),
    confirm_all: bool = typer.Option(False, "--confirm-all", help="Required with --all to prevent accidental bulk transfer."),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Disable prompts; all required choices must be supplied as flags."),
) -> None:
    """Build and review a transfer plan. This command does not move project state yet."""
    store = _store()
    try:
        if source is None:
            if non_interactive:
                raise ValueError("--from is required in --non-interactive mode")
            resolved_source = _prompt_source()
        else:
            resolved_source = _parse_source(source)

        if session is None and not project and not all_projects:
            if non_interactive:
                raise ValueError("Select --session, at least one --project, or --all in --non-interactive mode")
            session, project, all_projects, confirm_all = _prompt_session_or_projects(store, resolved_source)

        if all_projects and not confirm_all and not non_interactive:
            count = len(list_registered_projects(store))
            confirm_all = typer.confirm(
                f"You selected ALL {count} registered projects. Continue with all projects?",
                default=False,
            )

        if destination is None:
            if non_interactive:
                raise ValueError("--to is required in --non-interactive mode")
            destination = _prompt_destination()

        if session is not None:
            if all_projects:
                raise ValueError("--session cannot be combined with --all")
            if len(project) > 1:
                raise ValueError("A source session can be associated with only one explicit --project")
            review = build_session_transfer_review(
                store,
                source=resolved_source,
                destination=destination,
                session_id=session,
                project_selector=project[0] if project else None,
            )
            console.print(review.summary())
            console.print(f"Association evidence: {review.association_detail}")
            console.print("[yellow]Review only: no project state or session content was transferred.[/yellow]")
            return

        plan = build_transfer_plan(
            store,
            source=resolved_source,
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
