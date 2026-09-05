from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from .claude_atspi_probe import probe_claude_atspi

app = typer.Typer(add_completion=False, help="Probe Claude Desktop accessibility readiness without reading UI content.")
console = Console()


@app.callback(invoke_without_command=True)
def main() -> None:
    item = probe_claude_atspi()
    table = Table(title="Claude Desktop AT-SPI readiness — no UI content read")
    table.add_column("Check")
    table.add_column("Result")
    table.add_row("gdbus available", "YES" if item.gdbus_available else "NO")
    table.add_row("busctl available", "YES" if item.busctl_available else "NO")
    table.add_row("Accessibility bus available", "YES" if item.accessibility_bus_available else "NO")
    table.add_row(
        "Accessibility enabled",
        "YES" if item.accessibility_enabled is True else "NO" if item.accessibility_enabled is False else "UNKNOWN",
    )
    table.add_row("AT-SPI bus address available", "YES" if item.accessibility_bus_address_available else "NO")
    table.add_row("AT-SPI registry available", "YES" if item.registry_available else "NO")
    table.add_row("Claude registration signal", "YES" if item.claude_registered else "NOT OBSERVED")
    table.add_row("Safe for next tree probe", "YES" if item.safe_for_tree_probe else "NO")
    console.print(table)

    if item.safe_for_tree_probe:
        console.print("[green]AT-SPI is ready for a bounded read-only accessibility-tree probe.[/green]")
    else:
        console.print("[yellow]AT-SPI is not ready yet. No Claude UI content was read.[/yellow]")
    console.print("[dim]This command does not read project names, instructions, conversations, files, cookies, tokens, cache values, or DOM content.[/dim]")


if __name__ == "__main__":
    app()
