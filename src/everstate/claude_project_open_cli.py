from __future__ import annotations

import typer
from rich.console import Console

from .claude_desktop_authorized import open_claude_exact_project

app = typer.Typer(add_completion=False, help="Open one exact Claude Desktop project by source-native UUID.")
console = Console()


@app.command()
def main(project_id: str = typer.Argument(..., help="Claude project UUID.")) -> None:
    result = open_claude_exact_project(project_id)
    if not result.valid_project_id:
        console.print("[red]Invalid Claude project UUID. No navigation was attempted.[/red]")
        raise typer.Exit(code=2)
    if not result.attempted:
        console.print("[red]Claude project navigation could not be attempted because the claude:// handler or OS opener is unavailable.[/red]")
        raise typer.Exit(code=3)
    if result.exit_code != 0:
        console.print(f"[red]OS handoff failed with exit code {result.exit_code}.[/red]")
        raise typer.Exit(code=4)
    console.print(f"[green]OS accepted exact Claude project handoff for {result.project_id}.[/green]")
    console.print("[yellow]Verify visually that Claude Desktop opened the expected project. This proves exact-project UI navigation, not programmatic project-content access.[/yellow]")


if __name__ == "__main__":
    app()
