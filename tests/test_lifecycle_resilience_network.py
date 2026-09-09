from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import typer
from typer.testing import CliRunner

from everstate.execution_fabric_continuation import ExecutionFabricError
from everstate.provider_fabric import FabricHealth
from everstate.service import EverstateService
from everstate.storage import LocalStore
from everstate.work_start_cli import register


READY = FabricHealth("READY", True, "ready")


class FakeFabric:
    def __init__(self, name: str):
        self.name = name


def _app(service: EverstateService) -> typer.Typer:
    app = typer.Typer()
    register(app, lambda: service)
    return app


def test_network_loss_after_checkpoint_falls_to_local_without_state_drift(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "release"
    root.mkdir()
    service = EverstateService(LocalStore(tmp_path / "everstate.db"))
    service.set_objective(root, "Complete release despite WAN outage")

    fabrics = {name: FakeFabric(name) for name in ("ypipe", "freellmapi", "omniroute")}
    monkeypatch.setattr(
        "everstate.work_start_cli._safe_fabric",
        lambda name, factory: (fabrics[name], READY),
    )
    monkeypatch.setattr("everstate.work_start_cli.configured_policy", lambda: "cloud-preferred")
    attempts: list[str] = []

    def execute(fabric, packet, verify_identity=True):
        attempts.append(fabric.name)
        if fabric.name in {"omniroute", "freellmapi"}:
            raise ExecutionFabricError("network unreachable after checkpoint")
        return SimpleNamespace(
            fabric="ypipe",
            target="local-model",
            verified_identity=True,
            response={
                "everstate_project_id": packet.project_id,
                "everstate_state_version": packet.state_version,
            },
        )

    monkeypatch.setattr("everstate.work_start_cli.execute_fabric_continuation", execute)
    result = CliRunner().invoke(
        _app(service),
        ["Deploy release candidate", "--path", str(root), "--next-action", "Verify local build artifacts"],
    )

    assert result.exit_code == 0, result.output
    assert attempts == ["omniroute", "freellmapi", "ypipe"]
    state = service.status(root)
    assert state.objective == "Complete release despite WAN outage"
    assert state.current_task == "Deploy release candidate"
    assert state.next_action == "Verify local build artifacts"


def test_no_cloud_project_does_not_probe_remote_execution_after_restart(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "airgapped"
    root.mkdir()
    db = tmp_path / "everstate.db"
    first = EverstateService(LocalStore(db))
    first.add_constraint(root, "AIRGAPPED")
    first.set_task(root, "Inspect offline model output")

    restarted = EverstateService(LocalStore(db))
    fabrics = {name: FakeFabric(name) for name in ("ypipe", "freellmapi", "omniroute")}
    monkeypatch.setattr(
        "everstate.work_start_cli._safe_fabric",
        lambda name, factory: (fabrics[name], READY),
    )
    monkeypatch.setattr("everstate.work_start_cli.configured_policy", lambda: "cloud-preferred")
    attempts: list[str] = []

    def fail_local(fabric, packet, verify_identity=True):
        attempts.append(fabric.name)
        raise ExecutionFabricError("local runtime unavailable")

    monkeypatch.setattr("everstate.work_start_cli.execute_fabric_continuation", fail_local)
    result = CliRunner().invoke(
        _app(restarted),
        ["Continue offline investigation", "--path", str(root)],
    )

    assert result.exit_code == 2
    assert attempts == ["ypipe"]
    assert restarted.status(root).active_constraints == ["AIRGAPPED"]
