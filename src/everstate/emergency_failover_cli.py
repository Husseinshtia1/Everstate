from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .emergency_failover import prepare_emergency_failover
from .service import EverstateService
from .storage import LocalStore

app = typer.Typer(help="Prepare a source-independent Everstate emergency continuation bundle.")
console = Console()


def _service() -> EverstateService:
    return EverstateService(LocalStore(Path.home() / ".everstate" / "everstate.db"))


@app.command()
def main(
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
    source: str = typer.Option(..., "--source", help="Unavailable source provider, e.g. claude."),
    target: str = typer.Option(..., "--target", help="Destination provider, e.g. codex."),
    output_root: Path | None = typer.Option(None, "--output-root", file_okay=False),
) -> None:
    """Create a verified continuation bundle without calling the failed source AI."""
    result = prepare_emergency_failover(
        service=_service(),
        root=path,
        source_provider=source,
        target_provider=target,
        output_root=output_root,
    )
    table = Table(title="Everstate emergency failover")
    table.add_column("Gate")
    table.add_column("Result")
    table.add_row("Project", result.project_id)
    table.add_row("State version", str(result.state_version))
    table.add_row("Unavailable source", result.source_provider)
    table.add_row("Destination", result.target_provider)
    table.add_row("Source contacted", "NO")
    table.add_row("Continuation JSON", str(result.json_path))
    table.add_row("Continuation Markdown", str(result.markdown_path))
    table.add_row("Integrity manifest", str(result.manifest_path))
    console.print(table)
    console.print("[green]Failover bundle prepared from Everstate canonical state only.[/green]")
    console.print("[dim]This command does not launch or probe the unavailable source provider.[/dim]")


if __name__ == "__main__":
    app()
