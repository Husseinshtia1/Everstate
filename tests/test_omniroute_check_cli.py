from __future__ import annotations

import json

from typer.testing import CliRunner

import everstate.omniroute_check_cli as check_cli
from everstate.cli_runtime import app
from everstate.provider_readiness import ProviderCapability, ProviderProbeResult, ProviderState
from everstate.providers import ProviderAdapter

runner = CliRunner()


def _probe(state: ProviderState, *, ready_detail: str = "detail") -> ProviderProbeResult:
    return ProviderProbeResult(
        key="codex-omniroute",
        name="Codex via OmniRoute",
        state=state,
        detail=ready_detail,
        executable="/tmp/omniroute",
        capability=ProviderCapability(coding_agent=True, repository_access=True),
        active_check=True,
    )


def test_omniroute_check_json_isolated_report(monkeypatch) -> None:
    monkeypatch.setenv("EVERSTATE_OMNIROUTE_MODEL", "cx/gpt-5.5")
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: f"/tmp/{self.executable}")
    monkeypatch.setattr(check_cli, "probe_provider", lambda key, provider, active=False: _probe(ProviderState.READY))

    result = runner.invoke(app, ["omniroute-check", "--active", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["key"] == "codex-omniroute"
    assert payload["state"] == "READY"
    assert payload["ready"] is True
    assert payload["active_check"] is True
    assert payload["selected_model"] == "cx/gpt-5.5"
    assert payload["command_preview"] == [
        "/tmp/omniroute",
        "run",
        "codex",
        "--model",
        "cx/gpt-5.5",
        "--",
        "EVERSTATE_OMNIROUTE_PREFLIGHT",
    ]


def test_omniroute_check_returns_two_when_not_ready(monkeypatch) -> None:
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: None)
    monkeypatch.setattr(
        check_cli,
        "probe_provider",
        lambda key, provider, active=False: _probe(ProviderState.NETWORK_UNAVAILABLE, ready_detail="connection refused"),
    )

    result = runner.invoke(app, ["omniroute-check", "--active", "--json"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ready"] is False
    assert payload["state"] == "NETWORK_UNAVAILABLE"
    assert "connection refused" in payload["detail"]
