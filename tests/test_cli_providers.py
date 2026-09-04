from __future__ import annotations

from typer.testing import CliRunner

import everstate.cli as cli_module
from everstate.cli import app
from everstate.provider_readiness import probe_manual_export


runner = CliRunner()


def test_providers_command_lists_manual_fallback() -> None:
    result = runner.invoke(app, ["providers"])

    assert result.exit_code == 0
    assert "Everstate continuity targets" in result.stdout
    assert "Manual export" in result.stdout
    assert "ALWAYS_READY" in result.stdout
    assert "Passive mode" in result.stdout


def test_providers_json_is_machine_readable() -> None:
    result = runner.invoke(app, ["providers", "--json"])

    assert result.exit_code == 0
    assert '"key": "manual"' in result.stdout
    assert '"state": "ALWAYS_READY"' in result.stdout
    assert '"active_check": false' in result.stdout
    assert '"checked_at"' in result.stdout


def test_providers_active_is_explicit_and_forwarded(monkeypatch) -> None:
    seen: dict[str, bool] = {}

    def fake_probe_all_providers(*, active: bool = False):
        seen["active"] = active
        return [probe_manual_export()]

    monkeypatch.setattr(cli_module, "probe_all_providers", fake_probe_all_providers)
    result = runner.invoke(app, ["providers", "--active"])

    assert result.exit_code == 0
    assert seen["active"] is True
    assert "Active health checks were requested" in result.stdout
