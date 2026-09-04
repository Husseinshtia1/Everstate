from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import everstate.cli as cli_module
from everstate.cli import app
from everstate.continuity import ContinuationPacket


runner = CliRunner()


def packet() -> ContinuationPacket:
    return ContinuationPacket(
        project_id="proj_test",
        state_version=7,
        objective="Continue anywhere",
        current_task="Move work safely",
        decisions=[],
        constraints=["Preserve truth"],
        failed_attempts=[],
        blockers=[],
        modified_files=[],
        unresolved_conflicts=[],
        next_action="Resume",
    )


class FakeService:
    def continuation_packet(self, path: Path) -> ContinuationPacket:
        return packet()


def test_export_command_writes_both_portable_formats(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli_module, "_service", lambda: FakeService())
    output = tmp_path / "portable"

    result = runner.invoke(
        app,
        ["export", "--path", str(tmp_path), "--output-dir", str(output)],
    )

    assert result.exit_code == 0
    assert "state v7" in result.stdout
    assert (output / "everstate-state-v7.md").exists()
    assert (output / "everstate-state-v7.json").exists()


def test_copy_command_reports_success_when_clipboard_exists(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli_module, "_service", lambda: FakeService())
    monkeypatch.setattr(cli_module, "copy_packet", lambda packet: "/usr/bin/wl-copy")

    result = runner.invoke(app, ["copy", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "copied to clipboard" in result.stdout
    assert "/usr/bin/wl-copy" in result.stdout


def test_copy_command_exports_when_clipboard_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli_module, "_service", lambda: FakeService())
    monkeypatch.setattr(cli_module, "copy_packet", lambda packet: None)

    result = runner.invoke(app, ["copy", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "No supported clipboard utility was detected" in result.stdout
    assert "portable files were exported" in result.stdout
    assert (tmp_path / ".everstate" / "exports" / "everstate-state-v7.md").exists()
    assert (tmp_path / ".everstate" / "exports" / "everstate-state-v7.json").exists()
