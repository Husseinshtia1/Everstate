from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .acceptance import ContinuityScenario, evaluate_scenario, seed_scenario
from .handoff import launch_handoff, prepare_handoff
from .provider_readiness import probe_all_providers
from .providers import get_provider
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
) -> None:
    """Discover continuity targets and show their current readiness."""
    results = probe_all_providers()
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
    console.print("[dim]Executable discovery is implemented first. Auth/quota/network probes arrive in M2.5B.[/dim]")


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
