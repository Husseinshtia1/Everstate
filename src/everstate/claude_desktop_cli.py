from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .claude_cloud_layout import diagnose_claude_cloud_layout
from .claude_desktop import (
    associate_claude_desktop_project,
    diagnose_claude_desktop_profiles,
    discover_claude_desktop_projects,
    probe_claude_cloud_cache,
)
from .claude_desktop_authorized import probe_claude_desktop_authorized
from .storage import LocalStore
from .transfer_plan import list_registered_projects

app = typer.Typer(help="Inspect Claude Desktop project sources without reading conversations or secrets.")
console = Console()


@app.callback()
def desktop_cli() -> None:
    return None


def _store() -> LocalStore:
    return LocalStore(Path.home() / ".everstate" / "everstate.db")


@app.command("authorized-probe")
def authorized_probe(
    open_projects: bool = typer.Option(
        False,
        "--open-projects",
        help="Explicitly hand Claude's documented project-list fallback deep link to Claude Desktop.",
    ),
) -> None:
    """Verify safe UI-level access to the user's current Claude Desktop session."""
    item = probe_claude_desktop_authorized(open_projects=open_projects)
    table = Table(title="Claude Desktop authorized-session probe")
    table.add_column("Check")
    table.add_column("Result")
    table.add_row("Desktop profile", "YES" if item.profile_exists else "NO")
    table.add_row("claude:// scheme handler", item.scheme_handler or "NOT FOUND")
    table.add_row("OS opener", item.opener or "NOT FOUND")
    table.add_row("Desktop process detected", "YES" if item.desktop_process_detected else "NO")
    table.add_row("Can attempt UI navigation", "YES" if item.can_attempt_ui_navigation else "NO")
    if item.navigation_attempted:
        table.add_row("Navigation attempted", "YES")
        table.add_row("Navigation exit code", str(item.navigation_exit_code))
    else:
        table.add_row("Navigation attempted", "NO")
    console.print(table)

    if item.navigation_attempted and item.navigation_exit_code == 0:
        console.print(
            "[green]The operating system accepted Claude's documented project deep link.[/green]"
        )
        console.print(
            "[yellow]Now verify visually that Claude Desktop opened the Projects surface. This proves UI navigation only; it does not prove programmatic project listing or data access.[/yellow]"
        )
    elif open_projects and not item.can_attempt_ui_navigation:
        console.print(
            "[red]Everstate could not safely attempt Claude Desktop UI navigation because a scheme handler or OS opener is missing.[/red]"
        )
    else:
        console.print(
            "[cyan]Dry probe only. Re-run with --open-projects to explicitly test Claude Desktop Projects UI navigation.[/cyan]"
        )

    console.print(
        "[dim]This probe does not read Cookies, tokens, IndexedDB values, Local Storage, conversations, project instructions, or project files.[/dim]"
    )


@app.command("diagnose")
def diagnose() -> None:
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
        console.print("[cyan]A claude.ai renderer profile exists. The projects visible in Claude Desktop may be cloud Projects rather than local Cowork spaces.[/cyan]")
    if not any(item.has_local_cowork_inventory for item in items):
        console.print("[yellow]No local Cowork spaces.json inventory was detected.[/yellow]")
    console.print("[dim]Diagnosis checks only file/directory existence and counts. It does not open Cookies, IndexedDB, Local Storage, project instructions, or conversations.[/dim]")


@app.command("cloud-probe")
def cloud_probe() -> None:
    items = probe_claude_cloud_cache()
    table = Table(title="Claude Desktop cloud cache probe — counts only")
    table.add_column("Profile root")
    table.add_column("Files", justify="right")
    table.add_column("Bytes", justify="right")
    table.add_column("project", justify="right")
    table.add_column("/projects/", justify="right")
    table.add_column("project_id", justify="right")
    table.add_column("project_uuid", justify="right")
    table.add_column("api/organizations", justify="right")
    table.add_column("UUID patterns", justify="right")
    table.add_column("Truncated")
    for item in items:
        table.add_row(
            str(item.profile_root), str(item.files_scanned), str(item.bytes_scanned),
            str(item.marker_counts.get("project", 0)), str(item.marker_counts.get("projects_path", 0)),
            str(item.marker_counts.get("project_id", 0)), str(item.marker_counts.get("project_uuid", 0)),
            str(item.marker_counts.get("api_organizations", 0)), str(item.uuid_pattern_count),
            "YES" if item.truncated else "NO",
        )
    console.print(table)
    if any(item.has_project_markers for item in items):
        console.print("[green]Project-related markers exist in the local claude.ai IndexedDB cache. A metadata-only local cloud-project extractor may be feasible.[/green]")
    else:
        console.print("[yellow]No convincing project markers were found in the bounded local cache scan. Everstate will not infer project names from this result.[/yellow]")
    console.print("[dim]This probe emits counts only. It does not print cached values, project names, messages, cookies, tokens, instructions, or conversation text.[/dim]")


@app.command("cloud-layout")
def cloud_layout() -> None:
    """Measure cache encoding and UUID/metadata proximity without revealing values."""
    items = diagnose_claude_cloud_layout()
    table = Table(title="Claude Desktop cloud cache layout — counts only")
    table.add_column("Profile")
    table.add_column("Files", justify="right")
    table.add_column("Bytes", justify="right")
    table.add_column("UUID ASCII", justify="right")
    table.add_column("UUID UTF16", justify="right")
    table.add_column("project A/U", justify="right")
    table.add_column("name A/U", justify="right")
    table.add_column("P≤1.5K", justify="right")
    table.add_column("P≤4K", justify="right")
    table.add_column("P≤16K", justify="right")
    table.add_column("P≤64K", justify="right")
    table.add_column("name≤4K", justify="right")
    table.add_column("Truncated")
    for item in items:
        table.add_row(
            str(item.profile_root), str(item.files_scanned), str(item.bytes_scanned),
            str(item.uuid_ascii), str(item.uuid_utf16le),
            f"{item.project_ascii}/{item.project_utf16le}", f"{item.name_ascii}/{item.name_utf16le}",
            str(item.uuid_with_project_1536), str(item.uuid_with_project_4096),
            str(item.uuid_with_project_16384), str(item.uuid_with_project_65536),
            str(item.uuid_with_name_4096), "YES" if item.truncated else "NO",
        )
    console.print(table)
    console.print("[dim]A/U = ASCII/UTF-16LE marker counts. P≤N = UUIDs with a project marker within N bytes. Values themselves are never printed.[/dim]")
    console.print("[dim]This command reads only claude.ai IndexedDB. It does not read Cookies, Local Storage, messages, instructions, or tokens.[/dim]")


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
