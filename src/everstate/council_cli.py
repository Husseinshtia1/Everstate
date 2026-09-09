from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .agent_council import CouncilError, CouncilMode, CouncilParticipant, execute_agent_council
from .execution_config import fabric_enabled
from .fabric_routing import constraints_require_local
from .freellmapi_fabric import FreeLLMAPIFabric
from .omniroute_fabric import OmniRouteFabric
from .provider_fabric import FabricHealth
from .service import EverstateService
from .ypipe_fabric import YpipeFabric

console = Console()

_DEFAULT_ROLES = ("architect", "critic", "verifier")


def _safe_fabric(name: str, factory):
    if not fabric_enabled(name):
        return None, FabricHealth("DISABLED", False, "Disabled by Everstate setup policy."), ()
    try:
        fabric = factory()
        health = fabric.health()
        targets = fabric.discover_targets() if health.ready else ()
        return fabric, health, targets
    except (ValueError, OSError, RuntimeError) as exc:
        return None, FabricHealth("UNAVAILABLE", False, str(exc)), ()


def _roles(value: str) -> tuple[str, ...]:
    roles = tuple(part.strip() for part in value.split(",") if part.strip())
    if not roles:
        raise typer.BadParameter("At least one council role is required", param_hint="--roles")
    if len(set(roles)) != len(roles):
        raise typer.BadParameter("Council roles must be unique", param_hint="--roles")
    return roles


def _council_state_is_stale(initial, latest) -> bool:
    return initial.project_id != latest.project_id or initial.state_version != latest.state_version


def _select_participants(packet, roles: tuple[str, ...], max_agents: int):
    local_only = constraints_require_local(packet.constraints)
    candidate_groups: list[tuple[object, tuple[str, ...]]] = []
    health_report = {}

    factories = (("ypipe", YpipeFabric),)
    if not local_only:
        factories += (("freellmapi", FreeLLMAPIFabric), ("omniroute", OmniRouteFabric))

    for name, factory in factories:
        fabric, health, targets = _safe_fabric(name, factory)
        health_report[name] = {
            "status": health.status,
            "ready": health.ready,
            "detail": health.detail,
            "targets": [target.id for target in targets],
        }
        if fabric is not None and health.ready and targets:
            candidate_groups.append((fabric, tuple(target.id for target in targets)))

    if local_only:
        health_report["freellmapi"] = {
            "status": "FORBIDDEN",
            "ready": False,
            "detail": "Canonical constraints require local execution.",
            "targets": [],
        }
        health_report["omniroute"] = {
            "status": "FORBIDDEN",
            "ready": False,
            "detail": "Canonical constraints require local execution.",
            "targets": [],
        }

    if not candidate_groups:
        reason = "No eligible local council participant is ready." if local_only else "No enabled council execution target is ready."
        raise CouncilError(reason)

    candidates: list[tuple[object, str]] = []
    depth = 0
    while True:
        added = False
        for fabric, models in candidate_groups:
            if depth < len(models):
                candidates.append((fabric, models[depth]))
                added = True
        if not added:
            break
        depth += 1

    limit = min(max_agents, len(roles), len(candidates))
    participants = []
    for index, role in enumerate(roles[:limit]):
        fabric, model = candidates[index]
        participants.append(
            CouncilParticipant(role=role, fabric=fabric, model=model, local=fabric.name == "ypipe")
        )
    return tuple(participants), health_report, local_only


def register(app: typer.Typer, service_factory) -> None:
    @app.command("council")
    def council(
        question: str = typer.Argument(..., help="Decision, design question, or claim for independent agent review."),
        path: Path = typer.Option(Path.cwd(), "--path", exists=True, file_okay=False),
        mode: CouncilMode = typer.Option(CouncilMode.PARALLEL_REVIEW, "--mode"),
        roles: str = typer.Option(",".join(_DEFAULT_ROLES), "--roles", help="Comma-separated independent council roles."),
        max_agents: int = typer.Option(3, "--max-agents", min=1, max=8),
        rounds: int = typer.Option(2, "--rounds", min=1, max=5, help="Used by debate mode; parallel review always runs one round."),
        min_successful: int | None = typer.Option(None, "--min-successful", min=1, max=8, help="Required successful agents per round; default is majority quorum."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show eligible agents without contacting any model."),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        """Ask multiple independent agents/models to review or debate one project decision."""
        service: EverstateService = service_factory()
        packet = service.continuation_packet(path)
        role_tuple = _roles(roles)
        try:
            participants, health, local_only = _select_participants(packet, role_tuple, max_agents)
        except CouncilError as exc:
            console.print(f"[red]AgentCouncil unavailable:[/red] {exc}")
            raise typer.Exit(code=2) from exc

        if min_successful is not None and min_successful > len(participants):
            raise typer.BadParameter(
                "--min-successful cannot exceed the selected participant count",
                param_hint="--min-successful",
            )

        plan = {
            "project_id": packet.project_id,
            "state_version": packet.state_version,
            "question": question,
            "mode": mode.value,
            "local_only": local_only,
            "participants": [
                {"id": item.id, "role": item.role, "fabric": item.fabric.name, "model": item.model}
                for item in participants
            ],
            "fabric_health": health,
            "canonical_state_mutated": False,
        }
        if dry_run:
            if json_output:
                console.print_json(json.dumps(plan))
            else:
                lines = [
                    f"Project: {packet.project_id}@{packet.state_version}",
                    f"Mode: {mode.value}",
                    f"Local only: {local_only}",
                    "Participants:",
                    *[f"- {item.role}: {item.fabric.name}/{item.model}" for item in participants],
                    "No model contacted.",
                ]
                console.print(Panel.fit("\n".join(lines), title="Everstate AgentCouncil plan"))
            return

        try:
            result = execute_agent_council(
                packet=packet,
                question=question,
                participants=participants,
                mode=mode,
                rounds=rounds,
                min_successful=min_successful,
            )
        except CouncilError as exc:
            console.print(f"[red]AgentCouncil failed:[/red] {exc}")
            console.print("[dim]No council response was allowed to mutate canonical Everstate state.[/dim]")
            raise typer.Exit(code=2) from exc

        latest = service.continuation_packet(path)
        state_stale = _council_state_is_stale(packet, latest)

        report = asdict(result)
        report["mode"] = result.mode.value
        report["state_stale"] = state_stale
        report["latest_state_version"] = latest.state_version
        if json_output:
            console.print_json(json.dumps(report))
            if state_stale:
                raise typer.Exit(code=3)
            return

        console.print(Panel.fit(
            f"Project: {result.project_id}@{result.state_version}\n"
            f"Mode: {result.mode.value}\n"
            f"Consensus: {result.consensus}\n"
            f"Average confidence: {result.average_confidence:.2f}\n"
            f"Evidence coverage: {result.evidence_coverage:.0%}\n"
            f"Opinions: {len(result.opinions)}\n"
            f"Participant failures: {len(result.failures)}\n"
            f"State stale: {state_stale}\n"
            "Canonical state mutated: False",
            title="Everstate AgentCouncil",
        ))
        for opinion in result.opinions:
            console.print(
                f"[bold]{opinion.role}[/bold] ({opinion.fabric}/{opinion.model}, round {opinion.round})\n"
                f"Verdict: {opinion.verdict.value}\n"
                f"Recommendation: {opinion.recommendation}\n"
                f"Reasoning: {opinion.reasoning}\n"
                f"Risks: {', '.join(opinion.risks) or 'None surfaced'}\n"
                f"Evidence: {', '.join(opinion.evidence) or 'None supplied'}\n"
            )
        if result.failures:
            console.print("[yellow]Participant failures (excluded from consensus):[/yellow]")
            for failure in result.failures:
                console.print(f"- round {failure.round} {failure.participant_id}: {failure.error}")
        if result.disagreements:
            console.print("[yellow]Disagreements:[/yellow]")
            for disagreement in result.disagreements:
                console.print(f"- {disagreement}")
        if state_stale:
            console.print(
                f"[red]Council result is stale: canonical state advanced from {packet.state_version} "
                f"to {latest.state_version}. Re-run the council before acting on it.[/red]"
            )
            raise typer.Exit(code=3)
