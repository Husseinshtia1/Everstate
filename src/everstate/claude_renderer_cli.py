from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from .claude_renderer_probe import probe_claude_renderer

app = typer.Typer(add_completion=False, help="Probe Claude Desktop renderer debugging readiness without reading project data.")
console = Console()


@app.command()
def main() -> None:
    item = probe_claude_renderer()
    table = Table(title="Claude Desktop renderer readiness — no content read")
    table.add_column("Check")
    table.add_column("Result")
    table.add_row("Claude processes", str(item.claude_processes))
    table.add_row("Remote debugging enabled", "YES" if item.remote_debugging_enabled else "NO")
    table.add_row("Debugging address", item.address or "NOT EXPLICIT")
    table.add_row("Debugging port", str(item.port) if item.port else "NOT FOUND")
    table.add_row("Loopback-only proven", "YES" if item.loopback_only else "NO")
    table.add_row("/json/list reachable", "YES" if item.json_endpoint_reachable else "NO")
    table.add_row("Renderer targets", str(item.target_count))
    table.add_row("Safe for next read-only probe", "YES" if item.safe_for_readonly_probe else "NO")
    console.print(table)

    if item.safe_for_readonly_probe:
        console.print("[green]A loopback-only Claude Desktop CDP channel is available for the next read-only renderer capability test.[/green]")
    elif item.remote_debugging_enabled and not item.loopback_only:
        console.print("[red]Remote debugging exists but is not explicitly loopback-only. Everstate will not use it.[/red]")
    else:
        console.print("[yellow]Claude Desktop is not currently exposing a proven loopback-only renderer debugging channel. No project data was read.[/yellow]")


if __name__ == "__main__":
    app()
