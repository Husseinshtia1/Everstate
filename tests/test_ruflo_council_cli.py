from __future__ import annotations

from pathlib import Path

import typer
from typer.testing import CliRunner

from everstate.agent_council import CouncilMode, CouncilParticipant, CouncilResult
from everstate.continuity import ContinuationPacket
from everstate.council_cli import register
from everstate.ruflo_orchestrator import RufloError, RufloHealth


class FakeFabric:
    name = "ypipe"


class FakeService:
    def __init__(self) -> None:
        self.packet = ContinuationPacket(project_id="proj_cli", state_version=9)

    def continuation_packet(self, path: Path) -> ContinuationPacket:
        return self.packet


def _result() -> CouncilResult:
    return CouncilResult(
        project_id="proj_cli",
        state_version=9,
        question="Review this",
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


def _app(service: FakeService) -> typer.Typer:
    app = typer.Typer()
    register(app, lambda: service)

    @app.command("noop")
    def noop() -> None:
        return None

    return app


def _patch_participants(monkeypatch) -> None:
    participant = CouncilParticipant(role="architect", fabric=FakeFabric(), model="local", local=True)  # type: ignore[arg-type]
    monkeypatch.setattr(
        "everstate.council_cli._select_participants",
        lambda packet, roles, max_agents: ((participant,), {"ypipe": {"ready": True}}, False),
    )
    monkeypatch.setattr("everstate.council_cli.execute_agent_council", lambda **kwargs: _result())


def test_auto_falls_back_to_native_when_ruflo_prepare_fails(monkeypatch, tmp_path: Path) -> None:
    service = FakeService()
    _patch_participants(monkeypatch)

    class BrokenRuflo:
        def health(self):
            return RufloHealth(True, "3.41.1", "ready")

        def prepare_council(self, **kwargs):
            raise RufloError("simulated swarm failure")

    monkeypatch.setattr("everstate.council_cli.RufloOrchestrator", BrokenRuflo)
    result = CliRunner().invoke(
        _app(service),
        ["council", "Review this", "--path", str(tmp_path), "--orchestrator", "auto", "--json"],
    )

    assert result.exit_code == 0, result.output
    assert '"backend": "native"' in result.output
    assert "simulated swarm failure" in result.output


def test_forced_ruflo_fails_closed_when_unavailable(monkeypatch, tmp_path: Path) -> None:
    service = FakeService()
    _patch_participants(monkeypatch)

    class MissingRuflo:
        def health(self):
            return RufloHealth(False, None, "ruflo missing")

    monkeypatch.setattr("everstate.council_cli.RufloOrchestrator", MissingRuflo)
    result = CliRunner().invoke(
        _app(service),
        ["council", "Review this", "--path", str(tmp_path), "--orchestrator", "ruflo"],
    )

    assert result.exit_code == 2
    assert "Ruflo unavailable" in result.output
    assert "ruflo missing" in result.output


def test_native_mode_never_initializes_ruflo_swarm(monkeypatch, tmp_path: Path) -> None:
    service = FakeService()
    _patch_participants(monkeypatch)
    prepared = {"count": 0}

    class ReadyRuflo:
        def health(self):
            return RufloHealth(True, "3.41.1", "ready")

        def prepare_council(self, **kwargs):
            prepared["count"] += 1
            raise AssertionError("native mode must not prepare Ruflo")

    monkeypatch.setattr("everstate.council_cli.RufloOrchestrator", ReadyRuflo)
    result = CliRunner().invoke(
        _app(service),
        ["council", "Review this", "--path", str(tmp_path), "--orchestrator", "native", "--json"],
    )

    assert result.exit_code == 0, result.output
    assert prepared["count"] == 0
    assert '"backend": "native"' in result.output
