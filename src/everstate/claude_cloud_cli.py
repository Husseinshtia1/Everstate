from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from .claude_cloud_projects import discover_claude_cloud_project_candidates

app = typer.Typer(help="Review Claude Desktop cloud-project candidates from local cache only.")
console = Console()


@app.callback(invoke_without_command=True)
def candidates(
    json_output: bool = typer.Option(False, "--json", help="Print candidate metadata as JSON."),
    strict_only: bool = typer.Option(False, "--strict-only", help="Show only STRICT candidates."),
) -> None:
    """Show bounded local cache candidates; never reads Cookies or calls Claude APIs."""
    items = discover_claude_cloud_project_candidates()
    if strict_only:
        items = [item for item in items if item.selectable]

    if json_output:
        typer.echo(json.dumps([
            {
                "project_id": item.project_id,
                "name": item.name,
                "confidence": item.confidence,
                "selectable": item.selectable,
                "evidence": list(item.evidence),
                "source_file": item.source_file.name,
                "source_surface": "claude-desktop-cloud-cache",
            }
            for item in items
        ], indent=2))
        return

    table = Table(title="Claude Desktop cloud project candidates — local cache review")
    table.add_column("#")
    table.add_column("Name")
    table.add_column("Project UUID")
    table.add_column("Confidence")
    table.add_column("Selectable")
    for index, item in enumerate(items, start=1):
        style = "green" if item.confidence == "STRICT" else "yellow"
        table.add_row(
            str(index),
            item.name or "—",
            item.project_id,
            f"[{style}]{item.confidence}[/{style}]",
            "YES" if item.selectable else "NO",
        )
    console.print(table)

    strict_count = sum(1 for item in items if item.selectable)
    unverified_count = len(items) - strict_count
    console.print(f"STRICT: {strict_count}  UNVERIFIED: {unverified_count}")
    console.print(
        "[dim]STRICT means UUID + project marker + name/title were found in the same bounded cache window. "
        "UNVERIFIED candidates are review-only and must never be auto-selected for transfer.[/dim]"
    )
    console.print(
        "[dim]This command reads only Claude's local claude.ai IndexedDB cache. It does not read Cookies, Local Storage, conversations, instructions, or call private APIs.[/dim]"
    )


if __name__ == "__main__":
    app()
