from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .acceptance import AcceptanceReport, ContinuityScenario, evaluate_scenario, seed_scenario
from .agent_council import CouncilMode, CouncilResult, execute_agent_council
from .council_cli import _select_participants
from .handoff import write_handoff
from .providers import get_provider
from .ruflo_orchestrator import RufloError, RufloOrchestrator
from .service import EverstateService


class RealAcceptanceError(RuntimeError):
    pass


class StateLevel(StrEnum):
    MINIMAL = "minimal"
    OPERATIONAL = "operational"
    FULL = "full"


@dataclass(frozen=True)
class RealAcceptanceResult:
    scenario: str
    project_id: str
    initial_state_version: int
    final_state_version: int
    provider: str
    provider_exit_code: int
    orchestrator: str
    council_consensus: str | None
    acceptance: AcceptanceReport
    state_identity_preserved: bool
    canonical_state_advanced_during_agent_run: bool

    @property
    def passed(self) -> bool:
        return (
            self.provider_exit_code == 0
            and self.acceptance.passed
            and self.state_identity_preserved
            and not self.canonical_state_advanced_during_agent_run
        )

    def to_json(self) -> str:
        payload = {
            "scenario": self.scenario,
            "passed": self.passed,
            "project_id": self.project_id,
            "initial_state_version": self.initial_state_version,
            "final_state_version": self.final_state_version,
            "provider": self.provider,
            "provider_exit_code": self.provider_exit_code,
            "orchestrator": self.orchestrator,
            "council_consensus": self.council_consensus,
            "state_identity_preserved": self.state_identity_preserved,
            "canonical_state_advanced_during_agent_run": self.canonical_state_advanced_during_agent_run,
            "acceptance": self.acceptance.model_dump(mode="json"),
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )


def ensure_clean_baseline(root: Path, *, allow_dirty: bool = False) -> None:
    root = root.resolve()
    if not (root / ".git").exists():
        result = _run_git(root, "init")
        if result.returncode != 0:
            raise RealAcceptanceError(f"Could not initialize Git benchmark workspace: {result.stderr.strip()}")
        _run_git(root, "config", "user.name", "Everstate Acceptance")
        _run_git(root, "config", "user.email", "acceptance@localhost")
        _run_git(root, "add", ".")
        commit = _run_git(root, "commit", "-m", "Acceptance baseline")
        if commit.returncode != 0:
            raise RealAcceptanceError(f"Could not create Git benchmark baseline: {commit.stderr.strip()}")
        return

    status = _run_git(root, "status", "--porcelain")
    if status.returncode != 0:
        raise RealAcceptanceError(f"Could not inspect Git workspace: {status.stderr.strip()}")
    dirty = [line for line in status.stdout.splitlines() if line.strip() and ".everstate/" not in line and ".claude-flow/" not in line]
    if dirty and not allow_dirty:
        raise RealAcceptanceError(
            "Real acceptance requires a clean Git baseline; commit/stash existing changes or use --allow-dirty knowingly."
        )


def validate_state_level(scenario: ContinuityScenario, level: StateLevel) -> None:
    missing: list[str] = []
    if not scenario.objective.strip():
        missing.append("objective")
    if not scenario.current_task.strip():
        missing.append("current_task")
    if not scenario.next_action.strip():
        missing.append("next_action")
    if level in {StateLevel.OPERATIONAL, StateLevel.FULL} and not scenario.constraints:
        missing.append("constraints")
    if level is StateLevel.FULL:
        if not scenario.decisions:
            missing.append("decisions")
        if not scenario.failed_attempts:
            missing.append("failed_attempts")
        if not scenario.blockers:
            missing.append("blockers")
    if missing:
        raise RealAcceptanceError(
            f"Scenario does not satisfy state level {level.value}: missing {', '.join(missing)}"
        )


def _council_advisory(result: CouncilResult | None) -> str:
    if result is None:
        return "No council advisory was requested."
    lines = [
        "Advisory only; Everstate canonical state remains authoritative.",
        f"Council consensus: {result.consensus}",
        f"Evidence coverage: {result.evidence_coverage:.0%}",
    ]
    for opinion in result.opinions:
        lines.append(
            f"- {opinion.role}: verdict={opinion.verdict.value}; recommendation={opinion.recommendation}; risks={'; '.join(opinion.risks) or 'none'}"
        )
    return "\n".join(lines)


def _coding_prompt(packet, scenario: ContinuityScenario, council: CouncilResult | None) -> str:
    return (
        "You are the primary coding agent in an Everstate real acceptance run.\n"
        "Work directly in the current repository and implement the task completely.\n"
        "Inspect repository evidence before editing. Obey every canonical constraint.\n"
        "Do not edit .everstate or .claude-flow. Do not rewrite Everstate state.\n"
        "Run the project's validation commands before finishing.\n\n"
        "EVERSTATE CANONICAL CONTINUATION:\n"
        + packet.to_prompt()
        + "\n\nCOUNCIL ADVISORY (non-canonical):\n"
        + _council_advisory(council)
        + "\n\nACCEPTANCE EXPECTATIONS:\n"
        + f"Required changed files: {', '.join(scenario.required_changed_files) or 'scenario-defined'}\n"
        + f"Protected files: {', '.join(scenario.protected_files) or 'none'}\n"
        + "Complete the implementation, validate it, and stop."
    )


def run_real_acceptance(
    *,
    service: EverstateService,
    root: Path,
    scenario: ContinuityScenario,
    provider_name: str = "codex",
    state_level: StateLevel = StateLevel.FULL,
    council_enabled: bool = True,
    council_mode: CouncilMode = CouncilMode.PARALLEL_REVIEW,
    council_rounds: int = 2,
    orchestrator: str = "auto",
    max_agents: int = 3,
    allow_dirty: bool = False,
) -> RealAcceptanceResult:
    root = root.resolve()
    ensure_clean_baseline(root, allow_dirty=allow_dirty)
    validate_state_level(scenario, state_level)
    seed_scenario(service, root, scenario)
    packet = service.continuation_packet(root)
    initial_project_id = packet.project_id
    initial_state_version = packet.state_version

    council_result: CouncilResult | None = None
    orchestrator_used = "none"
    if council_enabled:
        participants, _, _ = _select_participants(
            packet, ("architect", "critic", "verifier"), max_agents
        )
        if orchestrator not in {"auto", "ruflo", "native"}:
            raise RealAcceptanceError("orchestrator must be auto, ruflo, or native")
        ruflo = RufloOrchestrator()
        health = ruflo.health()
        use_ruflo = orchestrator == "ruflo" or (orchestrator == "auto" and health.ready)
        if orchestrator == "ruflo" and not health.ready:
            raise RealAcceptanceError(f"Ruflo was required but is unavailable: {health.detail}")
        if use_ruflo:
            try:
                ruflo.prepare_council(
                    root=root,
                    packet=packet,
                    question=f"Review the implementation plan for: {scenario.current_task}",
                    participants=participants,
                    mode=council_mode,
                )
                orchestrator_used = "ruflo"
            except RufloError as exc:
                if orchestrator == "ruflo":
                    raise RealAcceptanceError(f"Ruflo orchestration failed: {exc}") from exc
                orchestrator_used = "native"
        else:
            orchestrator_used = "native"
        council_result = execute_agent_council(
            packet=packet,
            question=f"Review the implementation plan for: {scenario.current_task}",
            participants=participants,
            mode=council_mode,
            rounds=council_rounds,
        )
        if orchestrator_used == "ruflo":
            ruflo.verify_result(packet=packet, result=council_result)

    before_agent = service.continuation_packet(root)
    provider = get_provider(provider_name)
    if not provider.available():
        raise RealAcceptanceError(
            f"Primary coding provider {provider_name!r} is not available on this machine."
        )
    write_handoff(root, before_agent, provider)
    provider_exit_code = provider.launch(root, _coding_prompt(before_agent, scenario, council_result))

    after_agent = service.continuation_packet(root)
    report = evaluate_scenario(root, scenario)
    identity_preserved = after_agent.project_id == initial_project_id
    canonical_advanced = after_agent.state_version != before_agent.state_version

    return RealAcceptanceResult(
        scenario=scenario.name,
        project_id=initial_project_id,
        initial_state_version=initial_state_version,
        final_state_version=after_agent.state_version,
        provider=provider_name,
        provider_exit_code=provider_exit_code,
        orchestrator=orchestrator_used,
        council_consensus=council_result.consensus if council_result else None,
        acceptance=report,
        state_identity_preserved=identity_preserved,
        canonical_state_advanced_during_agent_run=canonical_advanced,
    )
