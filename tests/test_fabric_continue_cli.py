from __future__ import annotations

from pathlib import Path

import typer
from typer.testing import CliRunner

import everstate.fabric_continue_cli as fabric_continue_cli
from everstate.execution_fabric_continuation import ExecutionFabricContinuationResult
from everstate.fabric_continue_cli import register
from everstate.provider_fabric import FabricHealth
from everstate.service import EverstateService
from everstate.storage import LocalStore


runner = CliRunner()


def _service(tmp_path: Path) -> EverstateService:
    return EverstateService(LocalStore(tmp_path / "everstate.db"))


class ReadyYpipe:
    name = "ypipe"

    def health(self):
        return FabricHealth(status="READY", ready=True, detail="local ready")


class ReadyOmniRoute:
    name = "omniroute"

    def health(self):
        return FabricHealth(status="READY", ready=True, detail="cloud ready")


def test_dry_run_routes_without_executing_or_sending_state(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    service = _service(tmp_path)
    service.set_objective(root, "PRIVATE_WORK")
    app = typer.Typer()
    register(app, lambda: service)

    monkeypatch.setattr(fabric_continue_cli, "YpipeFabric", ReadyYpipe)
    monkeypatch.setattr(fabric_continue_cli, "OmniRouteFabric", ReadyOmniRoute)

    def forbidden_execute(*args, **kwargs):
        raise AssertionError("dry-run must not execute a continuation")

    monkeypatch.setattr(fabric_continue_cli, "execute_fabric_continuation", forbidden_execute)

    result = runner.invoke(app, ["--path", str(root), "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    assert '"selected": "ypipe"' in result.output
    assert '"executed": false' in result.output.lower()


def test_local_constraint_forbids_cloud_fallback(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    service = _service(tmp_path)
    service.add_constraint(root, "DATA_MUST_NOT_LEAVE_DEVICE")
    app = typer.Typer()
    register(app, lambda: service)

    class DownYpipe:
        name = "ypipe"

        def health(self):
            return FabricHealth(status="UNAVAILABLE", ready=False, detail="down")

    monkeypatch.setattr(fabric_continue_cli, "YpipeFabric", DownYpipe)
    monkeypatch.setattr(fabric_continue_cli, "OmniRouteFabric", ReadyOmniRoute)

    result = runner.invoke(app, ["--path", str(root), "--dry-run", "--json"])

    assert result.exit_code == 2
    assert '"selected": null' in result.output.lower()
    assert '"local_required": true' in result.output.lower()


def test_auto_executes_selected_ypipe_and_preserves_canonical_version(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    service = _service(tmp_path)
    service.set_task(root, "CONTINUE_ME")
    before = service.continuation_packet(root)
    app = typer.Typer()
    register(app, lambda: service)

    monkeypatch.setattr(fabric_continue_cli, "YpipeFabric", ReadyYpipe)
    monkeypatch.setattr(fabric_continue_cli, "OmniRouteFabric", ReadyOmniRoute)

    def fake_execute(fabric, packet, **kwargs):
        assert packet.project_id == before.project_id
        assert packet.state_version == before.state_version
        return ExecutionFabricContinuationResult(
            fabric="ypipe",
            target="local-model",
            verified_identity=True,
            response={
                "everstate_project_id": packet.project_id,
                "everstate_state_version": packet.state_version,
                "analysis": "ok",
                "proposed_next_action": "continue",
                "conflicts": [],
            },
        )

    monkeypatch.setattr(fabric_continue_cli, "execute_fabric_continuation", fake_execute)

    result = runner.invoke(app, ["--path", str(root), "--json"])

    assert result.exit_code == 0, result.output
    after = service.continuation_packet(root)
    assert after.state_version == before.state_version
    assert '"fabric": "ypipe"' in result.output
    assert '"canonical_state_mutated": false' in result.output.lower()
