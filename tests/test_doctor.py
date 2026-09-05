from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import everstate.doctor as doctor_module
from everstate.continuity import ContinuationPacket
from everstate.doctor import app, run_doctor
from everstate.provider_readiness import ProviderCapability, ProviderProbeResult, ProviderState


runner = CliRunner()


def packet() -> ContinuationPacket:
    return ContinuationPacket(
        project_id="proj_test",
        state_version=11,
        objective="Continue safely",
        current_task="Run the controlled handoff",
        decisions=[],
        constraints=["Preserve truth"],
        failed_attempts=[],
        blockers=[],
        modified_files=[],
        unresolved_conflicts=[],
        next_action="Continue",
    )


class FakeService:
    def continuation_packet(self, path: Path) -> ContinuationPacket:
        return packet()


def probe(
    key: str,
    *,
    state: ProviderState = ProviderState.READY,
    local: bool = False,
    cloud: bool = True,
    manual: bool = False,
    active_check: bool = False,
) -> ProviderProbeResult:
    return ProviderProbeResult(
        key=key,
        name=key,
        state=state,
        detail="test",
        executable=None if manual else f"/tmp/{key}",
        capability=ProviderCapability(
            coding_agent=not manual,
            repository_access=not manual,
            local=local,
            cloud=cloud,
            manual=manual,
        ),
        active_check=active_check,
    )


def test_doctor_passive_ready_is_not_enough_for_ai_test(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    report = run_doctor(
        tmp_path,
        service=FakeService(),
        probes=[
            probe("codex"),
            probe("manual", state=ProviderState.ALWAYS_READY, cloud=False, manual=True),
        ],
    )

    assert report.status == "AI_HEALTH_UNVERIFIED"
    assert report.ai_test_ready is False
    assert report.integrated_ready_targets == ("codex",)
    assert report.recommended_target == "codex"


def test_doctor_reports_ready_for_ai_test_only_after_active_health(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    report = run_doctor(
        tmp_path,
        active=True,
        service=FakeService(),
        probes=[
            probe("codex", active_check=True),
            probe("manual", state=ProviderState.ALWAYS_READY, cloud=False, manual=True),
        ],
    )

    assert report.status == "READY_FOR_AI_TEST"
    assert report.ai_test_ready is True
    assert report.state_ready is True
    assert report.portable_ready is True


def test_doctor_distinguishes_portable_only_from_blocked(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    report = run_doctor(
        tmp_path,
        service=FakeService(),
        probes=[
            probe("codex", state=ProviderState.AUTH_EXPIRED),
            probe("manual", state=ProviderState.ALWAYS_READY, cloud=False, manual=True),
        ],
    )

    assert report.status == "PORTABLE_ONLY"
    assert report.portable_ready is True
    assert report.integrated_ready_targets == ()


def test_doctor_blocks_non_git_path_even_if_provider_is_ready(tmp_path: Path) -> None:
    report = run_doctor(
        tmp_path,
        active=True,
        service=FakeService(),
        probes=[probe("codex", active_check=True)],
    )

    assert report.status == "BLOCKED"
    assert report.git_project is False


def test_doctor_cli_require_ai_rejects_passive_ready(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(doctor_module, "_service", lambda: FakeService())
    monkeypatch.setattr(
        doctor_module,
        "probe_all_providers",
        lambda active=False: [
            probe("codex", active_check=active),
            probe("manual", state=ProviderState.ALWAYS_READY, cloud=False, manual=True),
        ],
    )

    result = runner.invoke(app, ["--path", str(tmp_path), "--require-ai"])

    assert result.exit_code == 2
    assert "AI_HEALTH_UNVERIFIED" in result.stdout


def test_doctor_cli_require_ai_accepts_active_ready(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(doctor_module, "_service", lambda: FakeService())
    monkeypatch.setattr(
        doctor_module,
        "probe_all_providers",
        lambda active=False: [
            probe("codex", active_check=active),
            probe("manual", state=ProviderState.ALWAYS_READY, cloud=False, manual=True),
        ],
    )

    result = runner.invoke(app, ["--path", str(tmp_path), "--active", "--require-ai"])

    assert result.exit_code == 0
    assert "READY_FOR_AI_TEST" in result.stdout


def test_doctor_cli_require_ai_exits_nonzero_for_portable_only(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(doctor_module, "_service", lambda: FakeService())
    monkeypatch.setattr(
        doctor_module,
        "probe_all_providers",
        lambda active=False: [
            probe("codex", state=ProviderState.AUTH_EXPIRED, active_check=active),
            probe("manual", state=ProviderState.ALWAYS_READY, cloud=False, manual=True),
        ],
    )

    result = runner.invoke(app, ["--path", str(tmp_path), "--active", "--require-ai"])

    assert result.exit_code == 2
    assert "PORTABLE_ONLY" in result.stdout


def test_doctor_json_is_machine_readable(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(doctor_module, "_service", lambda: FakeService())
    monkeypatch.setattr(
        doctor_module,
        "probe_all_providers",
        lambda active=False: [probe("codex", active_check=active)],
    )

    result = runner.invoke(app, ["--path", str(tmp_path), "--active", "--json"])

    assert result.exit_code == 0
    assert '"status": "READY_FOR_AI_TEST"' in result.stdout
    assert '"recommended_target": "codex"' in result.stdout
