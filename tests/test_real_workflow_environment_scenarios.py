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


def _service(tmp_path: Path) -> EverstateService:
    return EverstateService(LocalStore(tmp_path / "runtime" / "everstate.db"))


def _app(service: EverstateService) -> typer.Typer:
    app = typer.Typer()
    register(app, lambda: service)
    return app


def _install_ready_fabrics(monkeypatch):
    fabrics = {name: FakeFabric(name) for name in ("ypipe", "freellmapi", "omniroute")}

    def fake_safe(name, factory):
        return fabrics[name], READY

    monkeypatch.setattr("everstate.work_start_cli._safe_fabric", fake_safe)
    monkeypatch.setattr("everstate.work_start_cli.configured_policy", lambda: "auto")
    return fabrics


def test_real_workspace_with_unicode_and_spaces_survives_checkpoint_and_resume(tmp_path: Path) -> None:
    root = tmp_path / "مشروع العميل 2026"
    root.mkdir()
    service = _service(tmp_path)

    service.set_objective(root, "إطلاق النسخة التجريبية دون فقدان السياق")
    service.set_task(root, "إصلاح تسجيل الدخول للمستخدمين الحاليين")
    service.add_constraint(root, "NO_CLOUD")
    service.add_failure(root, "إعادة كتابة طبقة المصادقة بالكامل كسرت الجلسات القديمة")
    service.set_next_action(root, "تشغيل اختبار callback الحالي أولاً")

    packet = service.continuation_packet(root)
    assert packet.objective == "إطلاق النسخة التجريبية دون فقدان السياق"
    assert packet.current_task == "إصلاح تسجيل الدخول للمستخدمين الحاليين"
    assert packet.constraints == ["NO_CLOUD"]
    assert "إعادة كتابة طبقة المصادقة" in packet.failed_attempts[0]
    assert packet.next_action == "تشغيل اختبار callback الحالي أولاً"


def test_real_provider_outage_falls_through_to_next_ready_fabric(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "customer-api"
    root.mkdir()
    service = _service(tmp_path)
    _install_ready_fabrics(monkeypatch)
    attempts: list[str] = []

    def fake_execute(fabric, packet, verify_identity=True):
        attempts.append(fabric.name)
        if fabric.name == "ypipe":
            raise ExecutionFabricError("local model crashed after health probe")
        if fabric.name == "freellmapi":
            return SimpleNamespace(
                fabric="freellmapi",
                target="free-model",
                verified_identity=True,
                response={"everstate_project_id": packet.project_id, "everstate_state_version": packet.state_version},
            )
        raise AssertionError("OmniRoute should not be reached after successful FreeLLMAPI fallback")

    monkeypatch.setattr("everstate.work_start_cli.execute_fabric_continuation", fake_execute)
    result = CliRunner().invoke(_app(service), ["Fix checkout outage", "--path", str(root)])

    assert result.exit_code == 0, result.output
    assert attempts == ["ypipe", "freellmapi"]
    assert "trying next policy-safe fabric" in result.output
    assert service.status(root).current_task == "Fix checkout outage"


def test_identity_drift_on_first_fabric_can_fail_over_without_mutating_state(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "billing"
    root.mkdir()
    service = _service(tmp_path)
    _install_ready_fabrics(monkeypatch)
    attempts: list[str] = []

    def fake_execute(fabric, packet, verify_identity=True):
        attempts.append(fabric.name)
        if fabric.name == "ypipe":
            raise ExecutionFabricError("did not preserve Everstate project/state identity")
        return SimpleNamespace(
            fabric=fabric.name,
            target="fallback-model",
            verified_identity=True,
            response={"everstate_project_id": packet.project_id, "everstate_state_version": packet.state_version},
        )

    monkeypatch.setattr("everstate.work_start_cli.execute_fabric_continuation", fake_execute)
    before = service.status(root).version
    result = CliRunner().invoke(_app(service), ["Reconcile invoices", "--path", str(root)])

    assert result.exit_code == 0, result.output
    assert attempts == ["ypipe", "freellmapi"]
    after = service.status(root)
    assert after.current_task == "Reconcile invoices"
    assert after.version > before
    assert "fallback-model" not in (after.decisions + after.active_constraints + after.failed_attempts)


def test_all_execution_fabrics_can_fail_without_losing_semantic_checkpoint(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "incident-response"
    root.mkdir()
    service = _service(tmp_path)
    _install_ready_fabrics(monkeypatch)
    attempts: list[str] = []

    def always_fail(fabric, packet, verify_identity=True):
        attempts.append(fabric.name)
        raise ExecutionFabricError(f"{fabric.name} unavailable during execution")

    monkeypatch.setattr("everstate.work_start_cli.execute_fabric_continuation", always_fail)
    result = CliRunner().invoke(
        _app(service),
        ["Contain production incident", "--path", str(root), "--next-action", "Inspect last known healthy deploy"],
    )

    assert result.exit_code == 2
    assert attempts == ["ypipe", "freellmapi", "omniroute"]
    state = service.status(root)
    assert state.current_task == "Contain production incident"
    assert state.next_action == "Inspect last known healthy deploy"
    assert "checkpoint remains persisted" in result.output.lower()


def test_local_only_failure_never_attempts_remote_fabrics(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "private-medical-data"
    root.mkdir()
    service = _service(tmp_path)
    service.add_constraint(root, "DATA_MUST_NOT_LEAVE_DEVICE")
    _install_ready_fabrics(monkeypatch)
    attempts: list[str] = []

    def local_failure(fabric, packet, verify_identity=True):
        attempts.append(fabric.name)
        raise ExecutionFabricError("local runtime exhausted memory")

    monkeypatch.setattr("everstate.work_start_cli.execute_fabric_continuation", local_failure)
    result = CliRunner().invoke(_app(service), ["Review private records pipeline", "--path", str(root)])

    assert result.exit_code == 2
    assert attempts == ["ypipe"]
    assert "freellmapi" not in result.output.lower().split("runtime fallback order:")[-1]
    assert service.status(root).current_task == "Review private records pipeline"


def test_cloud_preferred_runtime_failure_moves_to_free_then_local(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "marketing-site"
    root.mkdir()
    service = _service(tmp_path)
    _install_ready_fabrics(monkeypatch)
    monkeypatch.setattr("everstate.work_start_cli.configured_policy", lambda: "cloud-preferred")
    attempts: list[str] = []

    def fake_execute(fabric, packet, verify_identity=True):
        attempts.append(fabric.name)
        if fabric.name in {"omniroute", "freellmapi"}:
            raise ExecutionFabricError("remote provider transient failure")
        return SimpleNamespace(
            fabric="ypipe",
            target="local-model",
            verified_identity=True,
            response={"everstate_project_id": packet.project_id, "everstate_state_version": packet.state_version},
        )

    monkeypatch.setattr("everstate.work_start_cli.execute_fabric_continuation", fake_execute)
    result = CliRunner().invoke(_app(service), ["Generate launch copy", "--path", str(root)])

    assert result.exit_code == 0, result.output
    assert attempts == ["omniroute", "freellmapi", "ypipe"]
