from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .acceptance import ContinuityScenario, evaluate_scenario, seed_scenario
from .handoff import launch_handoff, prepare_handoff
from .portable import copy_packet, export_packet
from .provider_readiness import ProviderState, probe_all_providers, probe_executable_provider
from .providers import get_provider
from .routing import RoutingMode, rank_providers
from .routing_attempts import (
    RoutingAttempt,
    append_routing_attempt,
    classify_launch_outcome,
    next_eligible_after_failure,
    now_iso,
)
from .service import EverstateService
from .storage import LocalStore

app = typer.Typer(help="Everstate — local-first continuity for AI-assisted projects.")
console = Console()


def _db_path() -> Path:
    return Path.home() / ".everstate" / "everstate.db"


def _service() -> EverstateService:
    return EverstateService(LocalStore(_db_path()))


def _print_version(state_version: int) -> None:
    console.print(f"[green]Everstate state updated to v{state_version}[/green]")


def _print_ranked_targets(ranked) -> None:
    table = Table(title="Everstate continuation options")
    table.add_column("Rank")
    table.add_column("Target")
    table.add_column("State")
    table.add_column("Score")
    table.add_column("Recommendation")
    for item in ranked:
        rank = str(item.rank) if item.rank is not None else "—"
        score = f"{item.routing.score:.1f}" if item.routing.eligible else "—"
        recommendation = "Recommended" if item.recommended else ""
        style = "green" if item.probe.ready else "yellow"
        table.add_row(
            rank,
            item.probe.name,
            f"[{style}]{item.probe.state.value}[/{style}]",
            score,
            recommendation,
        )
    console.print(table)


def _audit_attempt(
    *,
    path: Path,
    packet,
    selected,
    mode: RoutingMode,
    selected_by: str,
    result: str,
    failure_class: ProviderState | None,
    returncode: int | None,
    started_at: str,
) -> Path:
    attempt = RoutingAttempt(
        project_id=packet.project_id,
        state_version=packet.state_version,
        target_key=selected.probe.key,
        target_name=selected.probe.name,
        routing_mode=mode.value,
        routing_score=selected.routing.score,
        selected_by=selected_by,
        result=result,
        failure_class=failure_class.value if failure_class is not None else None,
        returncode=returncode,
        started_at=started_at,
        finished_at=now_iso(),
    )
    return append_routing_attempt(path, attempt)


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
    console.print(f"Next action: {state.next_action or '[dim]not established[/dim]'}")
    console.print("Modified files:")
    if state.modified_files:
        for file in state.modified_files:
            console.print(f"  • {file}")
    else:
        console.print("  • [dim]working tree clean[/dim]")


@app.command("providers")
def providers_command(
    json_output: bool = typer.Option(False, "--json", help="Print provider readiness as JSON."),
    active: bool = typer.Option(
        False,
        "--active",
        help="Run opt-in provider health requests. These may consume a small amount of provider usage.",
    ),
) -> None:
    """Discover continuity targets and show their current readiness."""
    results = probe_all_providers(active=active)
    if json_output:
        typer.echo(
            json.dumps(
                [
                    {
                        "key": result.key,
                        "name": result.name,
                        "state": result.state.value,
                        "ready": result.ready,
                        "detail": result.detail,
                        "executable": result.executable,
                        "checked_at": result.checked_at.isoformat(),
                        "active_check": result.active_check,
                        "capability": {
                            "coding_agent": result.capability.coding_agent,
                            "repository_access": result.capability.repository_access,
                            "local": result.capability.local,
                            "cloud": result.capability.cloud,
                            "manual": result.capability.manual,
                        },
                    }
                    for result in results
                ],
                indent=2,
            )
        )
        return

    table = Table(title="Everstate continuity targets")
    table.add_column("Target")
    table.add_column("State")
    table.add_column("Details")
    for result in results:
        style = "green" if result.ready else "yellow"
        table.add_row(result.name, f"[{style}]{result.state.value}[/{style}]", result.detail)
    console.print(table)
    if active:
        console.print("[dim]Active health checks were requested. They use fixed health prompts and send no project state or source.[/dim]")
    else:
        console.print("[dim]Passive mode checks installation and local auth state. Use --active to test provider network/quota health.[/dim]")


@app.command("export")
def export_continuation(
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
    output_dir: Path | None = typer.Option(None, "--output-dir", file_okay=False),
) -> None:
    """Export the canonical continuation state as portable Markdown and JSON."""
    packet = _service().continuation_packet(path)
    result = export_packet(path, packet, output_dir)
    console.print(f"[green]Portable continuation exported for state v{packet.state_version}.[/green]")
    console.print(f"Markdown: {result.markdown_path}")
    console.print(f"JSON: {result.json_path}")


@app.command("copy")
def copy_continuation(
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
) -> None:
    """Copy the canonical continuation packet to the system clipboard when supported."""
    packet = _service().continuation_packet(path)
    executable = copy_packet(packet)
    if executable is not None:
        console.print(f"[green]Continuation state v{packet.state_version} copied to clipboard.[/green]")
        console.print(f"[dim]Clipboard tool: {executable}[/dim]")
        return

    result = export_packet(path, packet)
    console.print("[yellow]No supported clipboard utility was detected; portable files were exported instead.[/yellow]")
    console.print(f"Markdown: {result.markdown_path}")
    console.print(f"JSON: {result.json_path}")


@app.command("continue")
def continue_work(
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
    mode: RoutingMode = typer.Option(RoutingMode.AUTO, "--mode", case_sensitive=False),
    target: str | None = typer.Option(None, "--target", help="Explicit ready target key, such as codex or claude."),
    active_health: bool = typer.Option(
        False,
        "--active-health",
        help="Actively test provider network/quota health before ranking; may consume small provider usage.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show routing decision without launching a provider."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Launch the first selected target without confirmation."),
) -> None:
    """Find the safest available way to continue the current project."""
    probes = probe_all_providers(active=active_health)
    ranked = rank_providers(probes, mode)
    _print_ranked_targets(ranked)

    selected = None
    selected_by = "explicit" if target is not None else "recommended"
    if target is not None:
        selected = next((item for item in ranked if item.probe.key == target), None)
        if selected is None:
            raise typer.BadParameter(f"Unknown continuation target {target!r}.", param_hint="--target")
        if not selected.routing.eligible:
            raise typer.BadParameter(
                f"Target {target!r} is not ready: {selected.probe.state.value}.",
                param_hint="--target",
            )
    elif mode is not RoutingMode.ASK_ME:
        selected = next((item for item in ranked if item.recommended), None)

    if selected is None:
        console.print("[yellow]No target was selected automatically.[/yellow]")
        console.print("Use --target <key> after reviewing the ranked options.")
        return

    console.print(
        Panel.fit(
            f"[bold]{selected.probe.name}[/bold]\n"
            f"State: {selected.probe.state.value}\n"
            f"Routing score: {selected.routing.score:.1f}/100\n"
            f"Mode: {mode.value}",
            title="Recommended continuation",
        )
    )

    if selected.probe.capability.manual:
        console.print("[yellow]No integrated AI target is ready. Manual continuation is still available.[/yellow]")
        console.print(f"Run: everstate export --path {path.resolve()}")
        return

    if dry_run:
        console.print("[dim]Dry run only; no provider was launched.[/dim]")
        return

    if not yes and not typer.confirm(f"Continue with {selected.probe.name}?", default=True):
        console.print("Continuation cancelled; project state remains unchanged.")
        return

    service = _service()
    packet = service.continuation_packet(path)
    failed_keys: set[str] = set()

    while selected is not None and not selected.probe.capability.manual:
        provider = get_provider(selected.probe.key)
        started_at = now_iso()
        try:
            result = launch_handoff(path, packet, provider)
            returncode = result.returncode
            handoff_path = result.path
        except FileNotFoundError:
            returncode = None
            handoff_path = None
            failure_class = ProviderState.NOT_INSTALLED
            _audit_attempt(
                path=path,
                packet=packet,
                selected=selected,
                mode=mode,
                selected_by=selected_by,
                result="FAILED",
                failure_class=failure_class,
                returncode=returncode,
                started_at=started_at,
            )
        else:
            if returncode == 0:
                history_path = _audit_attempt(
                    path=path,
                    packet=packet,
                    selected=selected,
                    mode=mode,
                    selected_by=selected_by,
                    result="EXITED_ZERO",
                    failure_class=None,
                    returncode=returncode,
                    started_at=started_at,
                )
                console.print(f"Handoff: {handoff_path}")
                console.print(f"{provider.name} exited with code 0")
                console.print("[dim]Exit code 0 means the provider session exited cleanly; Everstate does not claim the project task is complete.[/dim]")
                console.print(f"[dim]Routing audit: {history_path}[/dim]")
                return

            post_probe = probe_executable_provider(selected.probe.key, provider, active=False)
            failure_class = classify_launch_outcome(returncode, post_probe)
            _audit_attempt(
                path=path,
                packet=packet,
                selected=selected,
                mode=mode,
                selected_by=selected_by,
                result="FAILED",
                failure_class=failure_class,
                returncode=returncode,
                started_at=started_at,
            )

        failed_keys.add(selected.probe.key)
        failure_text = failure_class.value if failure_class is not None else "UNKNOWN_FAILURE"
        console.print(f"[yellow]{selected.probe.name} could not continue: {failure_text}.[/yellow]")
        console.print("[dim]Project state remains safe; this provider is excluded from the current fallback chain.[/dim]")

        refreshed_packet = service.continuation_packet(path)
        if refreshed_packet.state_version != packet.state_version:
            console.print(
                f"[cyan]Repository evidence changed during the failed attempt; continuation state refreshed "
                f"from v{packet.state_version} to v{refreshed_packet.state_version}.[/cyan]"
            )
        packet = refreshed_packet

        next_target = next_eligible_after_failure(ranked, failed_keys)
        if next_target is None:
            console.print("[yellow]No additional continuation target is currently eligible.[/yellow]")
            console.print(f"Portable continuation remains available: everstate export --path {path.resolve()}")
            return

        if next_target.probe.capability.manual:
            console.print("[yellow]Integrated AI targets are exhausted. Portable continuation remains available.[/yellow]")
            console.print(f"Run: everstate export --path {path.resolve()}")
            return

        console.print(
            Panel.fit(
                f"[bold]{next_target.probe.name}[/bold]\n"
                f"State: {next_target.probe.state.value}\n"
                f"Routing score: {next_target.routing.score:.1f}/100",
                title="Next available fallback",
            )
        )
        if not typer.confirm(f"Try fallback {next_target.probe.name}?", default=True):
            console.print("Fallback cancelled; project state remains unchanged.")
            return

        selected = next_target
        selected_by = "fallback-confirmed"


@app.command("set-objective")
def set_objective(
    value: str = typer.Argument(..., help="The project's current objective."),
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
) -> None:
    """Record the current project objective as explicit user state."""
    _print_version(_service().set_objective(path, value).version)


@app.command("set-task")
def set_task(
    value: str = typer.Argument(..., help="The task currently being worked on."),
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
) -> None:
    """Record the current task."""
    _print_version(_service().set_task(path, value).version)


@app.command()
def decide(
    value: str = typer.Argument(..., help="An active project decision."),
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
) -> None:
    """Record an explicit active decision."""
    _print_version(_service().add_decision(path, value).version)


@app.command()
def constraint(
    value: str = typer.Argument(..., help="An active constraint the next AI must preserve."),
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
) -> None:
    """Record an active project constraint."""
    _print_version(_service().add_constraint(path, value).version)


@app.command()
def fail(
    value: str = typer.Argument(..., help="A failed approach and, ideally, why it failed."),
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
) -> None:
    """Record a failed attempt so future agents do not repeat it blindly."""
    _print_version(_service().add_failure(path, value).version)


@app.command()
def block(
    value: str = typer.Argument(..., help="A blocker preventing progress."),
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
) -> None:
    """Record a current blocker."""
    _print_version(_service().add_blocker(path, value).version)


@app.command("next")
def set_next(
    value: str = typer.Argument(..., help="The next expected action."),
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
) -> None:
    """Record the next expected action for continuation."""
    _print_version(_service().set_next_action(path, value).version)


@app.command()
def resume(path: Path = typer.Argument(Path.cwd(), exists=True, file_okay=False)) -> None:
    """Generate a compact human-facing continuation brief."""
    typer.echo(_service().resume_text(path))


@app.command()
def packet(
    path: Path = typer.Argument(Path.cwd(), exists=True, file_okay=False),
    json_output: bool = typer.Option(False, "--json", help="Print the canonical continuation packet as JSON."),
) -> None:
    """Generate the canonical AI-to-AI continuation packet."""
    service = _service()
    continuation = service.continuation_packet(path)
    if json_output:
        typer.echo(json.dumps(continuation.model_dump(mode="json"), indent=2))
        return
    typer.echo(continuation.to_prompt())


@app.command("switch")
def switch_provider(
    target: str = typer.Argument(..., help="Target AI provider: claude or codex."),
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
    dry_run: bool = typer.Option(False, "--dry-run", help="Prepare the handoff without launching the target AI."),
) -> None:
    """Prepare a crash-safe local handoff and optionally launch another AI tool."""
    provider = get_provider(target)
    packet = _service().continuation_packet(path)
    if dry_run:
        result = prepare_handoff(path, packet, provider)
        console.print(f"[green]Handoff prepared[/green]: {result.path}")
        console.print(f"Target: {provider.name}")
        return

    try:
        result = launch_handoff(path, packet, provider)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc), param_hint="target") from exc
    console.print(f"Handoff: {result.path}")
    console.print(f"{provider.name} exited with code {result.returncode}")


@app.command("acceptance-seed")
def acceptance_seed(
    scenario_file: Path = typer.Argument(..., exists=True, dir_okay=False),
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
) -> None:
    """Seed a benchmark project with an interrupted-task Everstate state."""
    scenario = ContinuityScenario.load(scenario_file)
    prompt = seed_scenario(_service(), path, scenario)
    console.print(f"[green]Seeded acceptance scenario[/green]: {scenario.name}")
    typer.echo(prompt)


@app.command("acceptance-evaluate")
def acceptance_evaluate(
    scenario_file: Path = typer.Argument(..., exists=True, dir_okay=False),
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
    json_output: bool = typer.Option(False, "--json", help="Print the full acceptance report as JSON."),
) -> None:
    """Evaluate observable project outcomes after a continuity handoff."""
    scenario = ContinuityScenario.load(scenario_file)
    report = evaluate_scenario(path, scenario)
    if json_output:
        typer.echo(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        status_text = "PASS" if report.passed else "FAIL"
        console.print(f"[bold]{status_text}[/bold] {report.scenario} — score {report.score:.0%}")
        for check in report.checks:
            marker = "✓" if check.passed else "✗"
            console.print(f" {marker} {check.name}: {check.details}")
    if not report.passed:
        raise typer.Exit(code=1)


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
