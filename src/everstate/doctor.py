from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .provider_readiness import ProviderProbeResult, probe_all_providers
from .routing import RoutingMode, rank_providers
from .service import EverstateService
from .storage import LocalStore


app = typer.Typer(
    help="Everstate preflight: verify project state, continuation targets, routing, and portable fallback before a real handoff.",
    invoke_without_command=True,
)
console = Console()


@dataclass(frozen=True)
class DoctorReport:
    status: str
    project_path: str
    git_project: bool
    state_ready: bool
    project_id: str | None
    state_version: int | None
    portable_ready: bool
    integrated_ready_targets: tuple[str, ...]
    recommended_target: str | None
    routing_mode: str
    active_health: bool
    providers: tuple[dict, ...]
    detail: str

    @property
    def ai_test_ready(self) -> bool:
        return self.status == "READY_FOR_AI_TEST"


def _db_path() -> Path:
    return Path.home() / ".everstate" / "everstate.db"


def _service() -> EverstateService:
    return EverstateService(LocalStore(_db_path()))


def _provider_payload(probe: ProviderProbeResult) -> dict:
    return {
        "key": probe.key,
        "name": probe.name,
        "state": probe.state.value,
        "ready": probe.ready,
        "detail": probe.detail,
        "executable": probe.executable,
        "active_check": probe.active_check,
        "capability": {
            "coding_agent": probe.capability.coding_agent,
            "repository_access": probe.capability.repository_access,
            "local": probe.capability.local,
            "cloud": probe.capability.cloud,
            "manual": probe.capability.manual,
        },
    }


def run_doctor(
    path: Path,
    *,
    active: bool = False,
    mode: RoutingMode = RoutingMode.AUTO,
    service: EverstateService | None = None,
    probes: list[ProviderProbeResult] | None = None,
) -> DoctorReport:
    root = path.resolve()
    git_project = (root / ".git").exists()
    state_ready = False
    project_id: str | None = None
    state_version: int | None = None
    portable_ready = False
    state_error: str | None = None

    try:
        packet = (service or _service()).continuation_packet(root)
        state_ready = True
        project_id = packet.project_id
        state_version = packet.state_version
        portable_ready = bool(packet.to_prompt().strip()) and bool(
            json.dumps(packet.model_dump(mode="json"), sort_keys=True)
        )
    except Exception as exc:  # doctor must report environmental failures instead of crashing
        state_error = f"{type(exc).__name__}: {exc}"

    provider_results = probes if probes is not None else probe_all_providers(active=active)
    ranked = rank_providers(provider_results, mode)
    integrated_ready = tuple(
        item.probe.key
        for item in ranked
        if item.routing.eligible and item.probe.ready and not item.probe.capability.manual
    )
    recommended = next(
        (
            item.probe.key
            for item in ranked
            if item.recommended and not item.probe.capability.manual
        ),
        None,
    )

    if not git_project or not state_ready or not portable_ready:
        status = "BLOCKED"
        reasons = []
        if not git_project:
            reasons.append("project path is not a Git working tree")
        if not state_ready:
            reasons.append(f"canonical state could not be generated ({state_error or 'unknown error'})")
        if not portable_ready:
            reasons.append("portable continuation serialization is unavailable")
        detail = "; ".join(reasons)
    elif integrated_ready and active:
        status = "READY_FOR_AI_TEST"
        detail = (
            f"Canonical state and portable fallback are ready; {len(integrated_ready)} integrated AI target(s) "
            "passed active health checks."
        )
    elif integrated_ready:
        status = "AI_HEALTH_UNVERIFIED"
        detail = (
            f"Canonical state and portable fallback are ready; {len(integrated_ready)} integrated AI target(s) "
            "look ready locally, but quota/network/model execution have not been actively verified. Run with --active before a controlled AI test."
        )
    else:
        status = "PORTABLE_ONLY"
        detail = "Canonical state and portable fallback are ready, but no integrated AI target is currently ready."

    return DoctorReport(
        status=status,
        project_path=str(root),
        git_project=git_project,
        state_ready=state_ready,
        project_id=project_id,
        state_version=state_version,
        portable_ready=portable_ready,
        integrated_ready_targets=integrated_ready,
        recommended_target=recommended,
        routing_mode=mode.value,
        active_health=active,
        providers=tuple(_provider_payload(result) for result in provider_results),
        detail=detail,
    )


def _render(report: DoctorReport) -> None:
    status_style = {
        "READY_FOR_AI_TEST": "green",
        "AI_HEALTH_UNVERIFIED": "cyan",
        "PORTABLE_ONLY": "yellow",
        "BLOCKED": "red",
    }[report.status]
    console.print(f"[bold {status_style}]{report.status}[/bold {status_style}]")
    console.print(f"Project: {report.project_path}")
    console.print(f"State: {'ready' if report.state_ready else 'blocked'}")
    if report.state_version is not None:
        console.print(f"State version: {report.state_version}")
    console.print(f"Portable fallback: {'ready' if report.portable_ready else 'blocked'}")
    console.print(f"Routing mode: {report.routing_mode}")
    console.print(f"Active health: {'yes' if report.active_health else 'no'}")
    console.print(f"Recommended AI target: {report.recommended_target or 'none'}")
    console.print(report.detail)

    table = Table(title="Provider preflight")
    table.add_column("Key")
    table.add_column("Target")
    table.add_column("State")
    table.add_column("Local/Cloud")
    table.add_column("Details")
    for provider in report.providers:
        capability = provider["capability"]
        locality = "manual" if capability["manual"] else ("local" if capability["local"] else "cloud")
        table.add_row(
            provider["key"],
            provider["name"],
            provider["state"],
            locality,
            provider["detail"],
        )
    console.print(table)


@app.callback(invoke_without_command=True)
def doctor_command(
    path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
    active: bool = typer.Option(False, "--active", help="Run opt-in active provider health checks."),
    mode: RoutingMode = typer.Option(RoutingMode.AUTO, "--mode", case_sensitive=False),
    require_ai: bool = typer.Option(
        False,
        "--require-ai",
        help="Exit non-zero unless at least one integrated AI target passed an active health check.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the full preflight report as JSON."),
) -> None:
    """Verify that Everstate is ready before beginning a controlled continuation test."""
    report = run_doctor(path, active=active, mode=mode)
    if json_output:
        typer.echo(json.dumps(asdict(report), indent=2))
    else:
        _render(report)

    if report.status == "BLOCKED":
        raise typer.Exit(code=1)
    if require_ai and not report.ai_test_ready:
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
