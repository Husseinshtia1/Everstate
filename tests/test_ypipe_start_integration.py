from __future__ import annotations

import json
from pathlib import Path

import typer
from typer.testing import CliRunner

import everstate.work_start_cli as work_start_cli
from everstate.service import EverstateService
from everstate.storage import LocalStore
from everstate.work_start_cli import register
from everstate.ypipe_continuation import YpipeContinuationResult, write_ypipe_handoff


runner = CliRunner()


def _service(tmp_path: Path) -> EverstateService:
    return EverstateService(LocalStore(tmp_path / "everstate.db"))


def test_write_ypipe_handoff_contains_versioned_canonical_envelope(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    service = _service(tmp_path)
    service.set_objective(root, "LOCAL_CONTINUITY")
    service.set_task(root, "VERIFY_LOCAL_PATH")
    service.set_next_action(root, "RUN_YPIPE")
    packet = service.continuation_packet(root)

    path = write_ypipe_handoff(root, packet)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.name == f"state-v{packet.state_version}-ypipe.json"
    assert payload["everstate"]["project_id"] == packet.project_id
    assert payload["everstate"]["state_version"] == packet.state_version
    assert payload["contract"]["canonical_state_mutation"] == "forbidden"


def test_start_ypipe_dry_run_persists_checkpoint_without_contacting_ypipe(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    service = _service(tmp_path)
    app = typer.Typer()
    register(app, lambda: service)

    class ForbiddenFabric:
        def __init__(self, *args, **kwargs):
            raise AssertionError("dry-run must not construct/contact Ypipe fabric")

    monkeypatch.setattr(work_start_cli, "YpipeFabric", ForbiddenFabric)
    # Typer promotes a single registered command to the root command in this
    # isolated test app, so invoke the command arguments directly.
    result = runner.invoke(
        app,
        [
            "LOCAL_TASK",
            "--path",
            str(root),
            "--target",
            "ypipe",
            "--objective",
            "LOCAL_OBJECTIVE",
            "--next-action",
            "LOCAL_NEXT",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    state = service.status(root)
    assert state.objective == "LOCAL_OBJECTIVE"
    assert state.current_task == "LOCAL_TASK"
    assert state.next_action == "LOCAL_NEXT"
    handoff = root / ".everstate" / "handoffs" / f"state-v{state.version}-ypipe.json"
    assert handoff.exists()
    assert "Ypipe was not contacted" in result.output


def test_start_ypipe_executes_only_after_checkpoint_is_persisted(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    service = _service(tmp_path)
    app = typer.Typer()
    register(app, lambda: service)
    observed = {}

    class FakeFabric:
        def __init__(self, config):
            observed["fabric_constructed"] = True

    def fake_execute(fabric, packet, **kwargs):
        state = service.status(root)
        observed["task_at_execution"] = state.current_task
        observed["next_at_execution"] = state.next_action
        observed["packet_version"] = packet.state_version
        return YpipeContinuationResult(
            mode="inference",
            target="local/model",
            verified_identity=True,
            response={
                "everstate_project_id": packet.project_id,
                "everstate_state_version": packet.state_version,
                "analysis": "ok",
            },
        )

    monkeypatch.setattr(work_start_cli, "YpipeFabric", FakeFabric)
    monkeypatch.setattr(work_start_cli, "execute_ypipe_continuation", fake_execute)

    result = runner.invoke(
        app,
        [
            "EXECUTE_LOCAL_TASK",
            "--path",
            str(root),
            "--target",
            "ypipe",
            "--objective",
            "EXECUTE_LOCAL_OBJECTIVE",
            "--next-action",
            "EXECUTE_LOCAL_NEXT",
        ],
    )

    assert result.exit_code == 0, result.output
    assert observed["fabric_constructed"] is True
    assert observed["task_at_execution"] == "EXECUTE_LOCAL_TASK"
    assert observed["next_at_execution"] == "EXECUTE_LOCAL_NEXT"
    assert observed["packet_version"] == service.status(root).version
    assert "identity verified: True" in result.output
