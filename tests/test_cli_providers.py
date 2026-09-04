from __future__ import annotations

from typer.testing import CliRunner

from everstate.cli import app


runner = CliRunner()


def test_providers_command_lists_manual_fallback() -> None:
    result = runner.invoke(app, ["providers"])

    assert result.exit_code == 0
    assert "Everstate continuity targets" in result.stdout
    assert "Manual export" in result.stdout
    assert "ALWAYS_READY" in result.stdout


def test_providers_json_is_machine_readable() -> None:
    result = runner.invoke(app, ["providers", "--json"])

    assert result.exit_code == 0
    assert '"key": "manual"' in result.stdout
    assert '"state": "ALWAYS_READY"' in result.stdout
