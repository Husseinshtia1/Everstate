from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from everstate.agent_council import CouncilMode, CouncilParticipant, CouncilResult
from everstate.continuity import ContinuationPacket
from everstate.ruflo_orchestrator import RufloConfig, RufloError, RufloHealth, RufloOrchestrator


class DummyFabric:
    name = "ypipe"


def participant(role: str) -> CouncilParticipant:
    return CouncilParticipant(role=role, fabric=DummyFabric(), model="local-model", local=True)  # type: ignore[arg-type]


def test_health_requires_v3(monkeypatch) -> None:
    orchestrator = RufloOrchestrator(RufloConfig(command=("claude-flow",)))
    monkeypatch.setattr(orchestrator, "_run", lambda *args, **kwargs: "claude-flow v3.41.1")
    health = orchestrator.health()
    assert health.ready is True
    assert health.version == "3.41.1"

    monkeypatch.setattr(orchestrator, "_run", lambda *args, **kwargs: "claude-flow 2.9.0")
    health = orchestrator.health()
    assert health.ready is False
    assert health.version == "2.9.0"


def test_health_fails_closed_when_command_is_missing() -> None:
    health = RufloOrchestrator(RufloConfig(command=None)).health()
    assert health.ready is False
    assert health.version is None


def test_parallel_review_creates_star_swarm_and_roles(monkeypatch, tmp_path: Path) -> None:
    orchestrator = RufloOrchestrator(RufloConfig(command=("claude-flow",)))
    monkeypatch.setattr(orchestrator, "health", lambda: RufloHealth(True, "3.41.1", "ready"))
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(orchestrator, "_run", lambda *args, **kwargs: calls.append(tuple(args)) or "ok")

    packet = ContinuationPacket(project_id="proj_demo", state_version=7)
    run = orchestrator.prepare_council(
        root=tmp_path,
        packet=packet,
        question="Ship the migration?",
        participants=(participant("architect"), participant("verifier")),
        mode=CouncilMode.PARALLEL_REVIEW,
    )

    assert run.topology == "star"
    assert run.strategy == "parallel"
    assert calls[0][:2] == ("swarm", "init")
    assert ("--topology", "star") == (calls[0][2], calls[0][3])
    assert calls[1][:2] == ("agent", "spawn")
    assert calls[2][:2] == ("agent", "spawn")
    assert calls[-1][:2] == ("task", "orchestrate")
    assert "Ship the migration?" in calls[-1][calls[-1].index("--task") + 1]


def test_debate_uses_mesh_and_balanced_strategy(monkeypatch, tmp_path: Path) -> None:
    orchestrator = RufloOrchestrator(RufloConfig(command=("claude-flow",)))
    monkeypatch.setattr(orchestrator, "health", lambda: RufloHealth(True, "3.41.1", "ready"))
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(orchestrator, "_run", lambda *args, **kwargs: calls.append(tuple(args)) or "ok")

    run = orchestrator.prepare_council(
        root=tmp_path,
        packet=ContinuationPacket(project_id="proj_demo", state_version=8),
        question="Debate storage architecture",
        participants=(participant("architect"), participant("critic")),
        mode=CouncilMode.DEBATE,
    )

    assert run.topology == "mesh"
    assert run.strategy == "balanced"
    assert "--priority" in calls[-1]
    assert calls[-1][calls[-1].index("--priority") + 1] == "high"


def test_local_only_never_sends_human_question_to_ruflo(monkeypatch, tmp_path: Path) -> None:
    orchestrator = RufloOrchestrator(RufloConfig(command=("claude-flow",)))
    monkeypatch.setattr(orchestrator, "health", lambda: RufloHealth(True, "3.41.1", "ready"))
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(orchestrator, "_run", lambda *args, **kwargs: calls.append(tuple(args)) or "ok")

    secret = "SECRET CUSTOMER DATA MUST STAY LOCAL"
    run = orchestrator.prepare_council(
        root=tmp_path,
        packet=ContinuationPacket(project_id="proj_private", state_version=2, constraints=["NO_CLOUD"]),
        question=secret,
        participants=(participant("security"),),
        mode=CouncilMode.PARALLEL_REVIEW,
    )

    flattened = "\n".join(" ".join(call) for call in calls)
    assert secret not in flattened
    assert "content redacted by sovereignty policy" in flattened
    assert run.redacted_for_local_only is True


def test_ruflo_never_receives_provider_credentials(monkeypatch, tmp_path: Path) -> None:
    orchestrator = RufloOrchestrator(RufloConfig(command=("claude-flow",)))
    monkeypatch.setattr(orchestrator, "health", lambda: RufloHealth(True, "3.41.1", "ready"))
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(orchestrator, "_run", lambda *args, **kwargs: calls.append(tuple(args)) or "ok")
    monkeypatch.setenv("EVERSTATE_FREELLMAPI_API_KEY", "super-secret-token")

    orchestrator.prepare_council(
        root=tmp_path,
        packet=ContinuationPacket(project_id="proj_demo", state_version=3),
        question="Review API design",
        participants=(participant("architect"),),
        mode=CouncilMode.PARALLEL_REVIEW,
    )

    assert "super-secret-token" not in "\n".join(" ".join(call) for call in calls)


def test_verify_result_preserves_everstate_authority() -> None:
    orchestrator = RufloOrchestrator(RufloConfig(command=("claude-flow",)))
    packet = ContinuationPacket(project_id="proj_demo", state_version=4)
    result = CouncilResult(
        project_id="proj_demo",
        state_version=4,
        question="q",
        mode=CouncilMode.PARALLEL_REVIEW,
        opinions=(),
        failures=(),
        consensus="NO_OPINIONS",
        disagreements=(),
        average_confidence=0.0,
        evidence_coverage=0.0,
        quorum_met=True,
        canonical_state_mutated=False,
    )
    orchestrator.verify_result(packet=packet, result=result)

    with pytest.raises(RufloError, match="identity drifted"):
        orchestrator.verify_result(packet=packet, result=replace(result, state_version=5))
    with pytest.raises(RufloError, match="mutate canonical"):
        orchestrator.verify_result(packet=packet, result=replace(result, canonical_state_mutated=True))
