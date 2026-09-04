from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .service import EverstateService
from .storage import LocalStore

app = typer.Typer(help="Everstate — local-first continuity for AI-assisted projects.")
console = Console()


def _db_path() -> Path:
    return Path.home() / ".everstate" / "everstate.db"


def _service() -> EverstateService:
    return EverstateService(LocalStore(_db_path()))


@app.command()
def init(path: Path = typer.Argument(Path.cwd(), exists=True, file_okay=False)) -> None:
    """Register a Git project locally and capture its first state snapshot."""
    project_id = _service().init_project(path)
    console.print(
        Panel.fit(
            f"Project registered locally\n[bold]{path.resolve()}[/bold]\n\nID: {project_id}",
            title="Everstate",
        )
    )


@app.command()
def status(
    path: Path = typer.Argument(Path.cwd(), exists=True, file_okay=False),
    json_output: bool = typer.Option(False, "--json", help="Print canonical state as JSON."),
) -> None:
    """Refresh and display the current locally observed project state."""
    state = _service().status(path)
    if json_output:
        typer.echo(json.dumps(state.model_dump(mode="json"), indent=2))
        return

    console.print(f"[bold]State v{state.version}[/bold]")
    console.print(f"Project: {path.resolve()}")
    console.print(f"Objective: {state.objective or '[dim]not established[/dim]'}")
    console.print(f"Current task: {state.current_task or '[dim]not established[/dim]'}")
    console.print("Modified files:")
    if state.modified_files:
        for file in state.modified_files:
            console.print(f"  • {file}")
    else:
        console.print("  • [dim]working tree clean[/dim]")


@app.command()
def resume(path: Path = typer.Argument(Path.cwd(), exists=True, file_okay=False)) -> None:
    """Generate a compact continuation brief from the current local state."""
    typer.echo(_service().resume_text(path))


@app.command()
def diff(path: Path = typer.Argument(Path.cwd(), exists=True, file_okay=False)) -> None:
    """Show locally observed Git changes for the project."""
    state = _service().status(path)
    console.print(f"[bold]Everstate state v{state.version}[/bold]")
    if not state.modified_files:
        console.print("No working-tree file changes detected.")
        return
    console.print("Changed/untracked files:")
    for file in state.modified_files:
        console.print(f"  • {file}")


if __name__ == "__main__":
    app()
