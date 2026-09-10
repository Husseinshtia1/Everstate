from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .acceptance import AcceptanceCheck, AcceptanceReport, ContinuityScenario, evaluate_scenario
from .agent_council import CouncilMode, CouncilResult, execute_agent_council
from .council_cli import _select_participants
from .providers import ProviderAdapter
from .ruflo_orchestrator import RufloError, RufloOrchestrator
from .service import EverstateService


class StateLevel(StrEnum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    FULL = "full"
    CRITICAL = "critical"


@dataclass(frozen=True)
class RealAcceptanceRun:
    workspace: Path
    project_id: str
    initial_state_version: int
    final_state_version: int
    state_level: StateLevel
    council_backend: str
    provider: str
    provider_returncode: int | None
    report: AcceptanceReport


def _git(root: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")


def prepare_workspace(template: Path, workspace: Path) -> Path:
    template = template.resolve()
    workspace = workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError(f"Acceptance workspace must be absent or empty: {workspace}")
    workspace.mkdir(parents=True, exist_ok=True)
    for source in template.iterdir():
        target = workspace / source.name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    _git(workspace, "init")
    _git(workspace, "config", "user.name", "Everstate Acceptance")
    _git(workspace, "config", "user.email", "acceptance@everstate.local")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "Acceptance baseline")
    return workspace


def seed_state(
    service: EverstateService,
    root: Path,
    scenario: ContinuityScenario,
    level: StateLevel,
) -> None:
    service.init_project(root)
    service.set_objective(root, scenario.objective)
    service.set_task(root, scenario.current_task)
    if level is StateLevel.MINIMAL:
        return
    for value in scenario.decisions:
        service.add_decision(root, value)
    for value in scenario.constraints:
        service.add_constraint(root, value)
    service.set_next_action(root, scenario.next_action)
    if level is StateLevel.STANDARD:
        return
    for value in scenario.failed_attempts:
        service.add_failure(root, value)
    for value in scenario.blockers:
        service.add_blocker(root, value)
    if level is StateLevel.CRITICAL:
        service.add_constraint(root, "EVERSTATE_ACCEPTANCE: require independent council review before implementation")


def _council_summary(result: CouncilResult) -> str:
    lines = [
        f"Consensus: {result.consensus}",
        f"Evidence coverage: {result.evidence_coverage:.0%}",
    ]
    if result.disagreements:
        lines.append("Disagreements: " + " | ".join(result.disagreements))
    for opinion in result.opinions:
        lines.append(
            f"{opinion.role} [{opinion.verdict.value}]: {opinion.recommendation}; "
            f"risks={', '.join(opinion.risks) or 'none'}"
        )
    return "\n".join(lines)


def run_council(
    *,
    service: EverstateService,
    root: Path,
    question: str,
    orchestrator: str,
) -> tuple[CouncilResult, str]:
    packet = service.continuation_packet(root)
    participants, _, _ = _select_participants(packet, ("architect", "critic", "verifier"), 3)
    ruflo = RufloOrchestrator()
    health = ruflo.health()
    selected = orchestrator.strip().lower()
    if selected not in {"auto", "ruflo", "native"}:
        raise ValueError("orchestrator must be auto, ruflo, or native")
    use_ruflo = selected == "ruflo" or (selected == "auto" and health.ready)
    if selected == "ruflo" and not health.ready:
        raise RufloError(health.detail)
    backend = "native"
    if use_ruflo:
        try:
            ruflo.prepare_council(
                root=root,
                packet=packet,
                question=question,
                participants=participants,
                mode=CouncilMode.PARALLEL_REVIEW,
            )
            backend = "ruflo"
        except RufloError:
            if selected == "ruflo":
                raise
            backend = "native"
    result = execute_agent_council(
        packet=packet,
        question=question,
        participants=participants,
        mode=CouncilMode.PARALLEL_REVIEW,
    )
    if backend == "ruflo":
        ruflo.verify_result(packet=packet, result=result)
    return result, backend


def primary_prompt(
    *,
    service: EverstateService,
    root: Path,
    scenario: ContinuityScenario,
    council: CouncilResult | None,
) -> str:
    packet = service.continuation_packet(root)
    advisory = _council_summary(council) if council is not None else "Council was not run."
    validations = "\n".join("- " + " ".join(item.command) for item in scenario.validation_commands)
    protected = ", ".join(scenario.protected_files) or "none"
    return f"""You are the primary implementation agent in an Everstate real acceptance run.

Your job is to IMPLEMENT the requested project changes in the current working directory, not merely describe them.
Inspect the repository first. Obey the canonical Everstate state and constraints. Do not edit .everstate or .claude-flow runtime data.
Protected files that must remain unchanged: {protected}.
Run the required validation commands before you finish. If a council recommendation conflicts with repository evidence or canonical constraints, canonical constraints and repository evidence win.

CANONICAL EVERSTATE PACKET
{packet.to_prompt()}

ADVISORY COUNCIL OUTPUT (non-canonical)
{advisory}

REQUIRED VALIDATIONS
{validations or '- none'}

Complete the implementation now. Leave the working tree with the finished implementation and tests.
"""


def _append_checks(
    report: AcceptanceReport,
    *,
    provider_returncode: int,
    project_id_before: str,
    project_id_after: str,
    state_version_before: int,
    state_version_after: int,
    constraints_before: tuple[str, ...],
    constraints_after: tuple[str, ...],
) -> AcceptanceReport:
    checks = list(report.checks)
    checks.extend(
        [
            AcceptanceCheck(
                name="primary-provider-exit",
                passed=provider_returncode == 0,
                details=f"exit={provider_returncode}",
            ),
            AcceptanceCheck(
                name="canonical-project-identity",
                passed=project_id_before == project_id_after,
                details=f"before={project_id_before} after={project_id_after}",
            ),
            AcceptanceCheck(
                name="canonical-state-not-mutated-by-agent",
                passed=state_version_before == state_version_after,
                details=f"before={state_version_before} after={state_version_after}",
            ),
            AcceptanceCheck(
                name="canonical-constraints-preserved",
                passed=constraints_before == constraints_after,
                details=f"before={constraints_before!r} after={constraints_after!r}",
            ),
        ]
    )
    passed_count = sum(check.passed for check in checks)
    return AcceptanceReport(
        scenario=report.scenario,
        passed=all(check.passed for check in checks),
        score=passed_count / len(checks) if checks else 1.0,
        checks=checks,
    )


def run_real_acceptance(
    *,
    service: EverstateService,
    template: Path,
    workspace: Path,
    scenario: ContinuityScenario,
    provider: ProviderAdapter,
    state_level: StateLevel = StateLevel.FULL,
    orchestrator: str = "auto",
    require_council: bool = True,
    dry_run: bool = False,
) -> RealAcceptanceRun:
    root = prepare_workspace(template, workspace)
    seed_state(service, root, scenario, state_level)
    before = service.continuation_packet(root)

    if dry_run:
        primary_prompt(service=service, root=root, scenario=scenario, council=None)
        return RealAcceptanceRun(
            workspace=root,
            project_id=before.project_id,
            initial_state_version=before.state_version,
            final_state_version=before.state_version,
            state_level=state_level,
            council_backend="not-run",
            provider=provider.name,
            provider_returncode=None,
            report=AcceptanceReport(scenario=scenario.name, passed=True, score=1.0, checks=[]),
        )

    council_result: CouncilResult | None = None
    council_backend = "off"
    if require_council:
        council_result, council_backend = run_council(
            service=service,
            root=root,
            question=(
                "Review the implementation plan for this acceptance task. Identify architecture, correctness, "
                "security, persistence, and test risks before the primary coding agent changes files."
            ),
            orchestrator=orchestrator,
        )

    prompt = primary_prompt(
        service=service,
        root=root,
        scenario=scenario,
        council=council_result,
    )
    returncode = provider.launch(root, prompt)
    after = service.continuation_packet(root)
    report = evaluate_scenario(root, scenario)
    report = _append_checks(
        report,
        provider_returncode=returncode,
        project_id_before=before.project_id,
        project_id_after=after.project_id,
        state_version_before=before.state_version,
        state_version_after=after.state_version,
        constraints_before=before.constraints,
        constraints_after=after.constraints,
    )
    return RealAcceptanceRun(
        workspace=root,
        project_id=before.project_id,
        initial_state_version=before.state_version,
        final_state_version=after.state_version,
        state_level=state_level,
        council_backend=council_backend,
        provider=provider.name,
        provider_returncode=returncode,
        report=report,
    )
