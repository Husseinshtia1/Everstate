from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from .acceptance import AcceptanceCheck, AcceptanceReport, ContinuityScenario, evaluate_scenario
from .agent_council import CouncilError, CouncilMode, CouncilResult, execute_agent_council
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
    artifacts_dir: Path
    project_id: str
    initial_state_version: int
    final_state_version: int
    state_level: StateLevel
    council_backend: str
    council_participants: int
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
    service.set_next_action(root, scenario.next_action)
    if level is StateLevel.MINIMAL:
        return
    for value in scenario.decisions:
        service.add_decision(root, value)
    for value in scenario.constraints:
        service.add_constraint(root, value)
    if level is StateLevel.STANDARD:
        return
    for value in scenario.failed_attempts:
        service.add_failure(root, value)
    for value in scenario.blockers:
        service.add_blocker(root, value)
    if level is StateLevel.CRITICAL:
        service.add_constraint(
            root,
            "EVERSTATE_ACCEPTANCE: independent council review is mandatory before implementation",
        )


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


def _council_payload(result: CouncilResult) -> dict[str, object]:
    return {
        "project_id": result.project_id,
        "state_version": result.state_version,
        "question": result.question,
        "mode": result.mode.value,
        "consensus": result.consensus,
        "disagreements": list(result.disagreements),
        "average_confidence": result.average_confidence,
        "evidence_coverage": result.evidence_coverage,
        "quorum_met": result.quorum_met,
        "canonical_state_mutated": result.canonical_state_mutated,
        "opinions": [
            {**asdict(opinion), "verdict": opinion.verdict.value}
            for opinion in result.opinions
        ],
        "failures": [asdict(failure) for failure in result.failures],
    }


def _resolve_council_preflight(
    *,
    service: EverstateService,
    root: Path,
    orchestrator: str,
    min_agents: int,
) -> tuple[tuple[object, ...], str, RufloOrchestrator]:
    packet = service.continuation_packet(root)
    participants, _, _ = _select_participants(
        packet,
        ("architect", "critic", "verifier"),
        3,
    )
    if len(participants) < min_agents:
        raise CouncilError(
            f"Real acceptance requires at least {min_agents} eligible council participants; "
            f"only {len(participants)} are ready."
        )

    selected = orchestrator.strip().lower()
    if selected not in {"auto", "ruflo", "native"}:
        raise ValueError("orchestrator must be auto, ruflo, or native")

    ruflo = RufloOrchestrator()
    health = ruflo.health()
    use_ruflo = selected == "ruflo" or (selected == "auto" and health.ready)
    if selected == "ruflo" and not health.ready:
        raise RufloError(health.detail)
    return participants, "ruflo" if use_ruflo else "native", ruflo


def run_council(
    *,
    service: EverstateService,
    root: Path,
    question: str,
    orchestrator: str,
    min_agents: int = 2,
    mode: CouncilMode = CouncilMode.DEBATE,
    rounds: int = 2,
) -> tuple[CouncilResult, str, int]:
    packet = service.continuation_packet(root)
    participants, backend, ruflo = _resolve_council_preflight(
        service=service,
        root=root,
        orchestrator=orchestrator,
        min_agents=min_agents,
    )

    if backend == "ruflo":
        try:
            ruflo.prepare_council(
                root=root,
                packet=packet,
                question=question,
                participants=participants,
                mode=mode,
            )
        except RufloError:
            if orchestrator.strip().lower() == "ruflo":
                raise
            backend = "native"

    result = execute_agent_council(
        packet=packet,
        question=question,
        participants=participants,
        mode=mode,
        rounds=rounds,
    )
    if backend == "ruflo":
        ruflo.verify_result(packet=packet, result=result)
    return result, backend, len(participants)


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


def _semantic_snapshot(packet) -> dict[str, object]:
    return {
        "project_id": packet.project_id,
        "objective": packet.objective,
        "current_task": packet.current_task,
        "decisions": tuple(packet.decisions),
        "constraints": tuple(packet.constraints),
        "failed_attempts": tuple(packet.failed_attempts),
        "blockers": tuple(packet.blockers),
        "next_action": packet.next_action,
    }


def _append_checks(
    report: AcceptanceReport,
    *,
    provider_returncode: int,
    before,
    after,
) -> AcceptanceReport:
    before_semantic = _semantic_snapshot(before)
    after_semantic = _semantic_snapshot(after)
    changed_fields = [
        key for key in before_semantic if before_semantic[key] != after_semantic[key]
    ]
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
                passed=before.project_id == after.project_id,
                details=f"before={before.project_id} after={after.project_id}",
            ),
            AcceptanceCheck(
                name="canonical-semantic-state-preserved",
                passed=not changed_fields,
                details=(
                    "semantic truth preserved"
                    if not changed_fields
                    else "changed fields: " + ", ".join(changed_fields)
                ),
            ),
            AcceptanceCheck(
                name="state-version-monotonic",
                passed=after.state_version >= before.state_version,
                details=f"before={before.state_version} after={after.state_version}",
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


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
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
    min_council_agents: int = 2,
    dry_run: bool = False,
) -> RealAcceptanceRun:
    if state_level is StateLevel.CRITICAL and not require_council:
        raise ValueError("critical state level requires independent council review")
    if min_council_agents < 1 or min_council_agents > 3:
        raise ValueError("min_council_agents must be between 1 and 3")

    root = prepare_workspace(template, workspace)
    seed_state(service, root, scenario, state_level)
    before = service.continuation_packet(root)
    artifacts = root / ".everstate" / "real-acceptance"
    _write_json(artifacts / "state-before.json", before.model_dump(mode="json"))

    council_result: CouncilResult | None = None
    council_backend = "off"
    council_participants = 0
    if require_council:
        participants, council_backend, ruflo = _resolve_council_preflight(
            service=service,
            root=root,
            orchestrator=orchestrator,
            min_agents=min_council_agents,
        )
        council_participants = len(participants)
        health = ruflo.health()
        _write_json(
            artifacts / "council-preflight.json",
            {
                "backend": council_backend,
                "participants": [participant.id for participant in participants],
                "ruflo": {
                    "ready": health.ready,
                    "version": health.version,
                    "detail": health.detail,
                },
            },
        )

    prompt = primary_prompt(
        service=service,
        root=root,
        scenario=scenario,
        council=None,
    )
    if dry_run:
        (artifacts / "primary-prompt-preview.txt").write_text(prompt, encoding="utf-8")
        report = AcceptanceReport(
            scenario=scenario.name,
            passed=True,
            score=1.0,
            checks=[
                AcceptanceCheck(
                    name="dry-run-preflight",
                    passed=True,
                    details=(
                        f"provider={provider.name}; council={council_backend}; "
                        f"participants={council_participants}; no model contacted"
                    ),
                )
            ],
        )
        return RealAcceptanceRun(
            workspace=root,
            artifacts_dir=artifacts,
            project_id=before.project_id,
            initial_state_version=before.state_version,
            final_state_version=before.state_version,
            state_level=state_level,
            council_backend=council_backend,
            council_participants=council_participants,
            provider=provider.name,
            provider_returncode=None,
            report=report,
        )

    if require_council:
        council_result, council_backend, council_participants = run_council(
            service=service,
            root=root,
            question=(
                "Review the implementation plan for this acceptance task. Identify architecture, correctness, "
                "security, persistence, and test risks before the primary coding agent changes files."
            ),
            orchestrator=orchestrator,
            min_agents=min_council_agents,
            mode=CouncilMode.DEBATE,
            rounds=2,
        )
        _write_json(artifacts / "council-result.json", _council_payload(council_result))

    prompt = primary_prompt(
        service=service,
        root=root,
        scenario=scenario,
        council=council_result,
    )
    (artifacts / "primary-prompt.txt").write_text(prompt, encoding="utf-8")

    returncode = provider.launch(root, prompt)
    after = service.continuation_packet(root)
    _write_json(artifacts / "state-after.json", after.model_dump(mode="json"))

    report = evaluate_scenario(root, scenario)
    report = _append_checks(
        report,
        provider_returncode=returncode,
        before=before,
        after=after,
    )
    _write_json(artifacts / "acceptance-report.json", report.model_dump(mode="json"))

    return RealAcceptanceRun(
        workspace=root,
        artifacts_dir=artifacts,
        project_id=before.project_id,
        initial_state_version=before.state_version,
        final_state_version=after.state_version,
        state_level=state_level,
        council_backend=council_backend,
        council_participants=council_participants,
        provider=provider.name,
        provider_returncode=returncode,
        report=report,
    )
