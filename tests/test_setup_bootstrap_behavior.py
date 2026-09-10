from __future__ import annotations

from types import SimpleNamespace

from everstate.provider_fabric import FabricHealth
from everstate import setup_wizard_cli


def test_free_needs_credentials_detects_401_and_bearer_messages() -> None:
    assert setup_wizard_cli._free_needs_credentials(
        FabricHealth(status="UNAVAILABLE", ready=False, detail="FreeLLMAPI HTTP 401: Unauthorized")
    )
    assert setup_wizard_cli._free_needs_credentials(
        FabricHealth(status="UNAVAILABLE", ready=False, detail="missing Bearer token")
    )
    assert not setup_wizard_cli._free_needs_credentials(
        FabricHealth(status="UNAVAILABLE", ready=False, detail="connection refused")
    )


def test_install_ruflo_uses_v3_claude_flow_package(monkeypatch) -> None:
    monkeypatch.setattr(setup_wizard_cli.shutil, "which", lambda name: "/usr/bin/npm" if name == "npm" else None)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(setup_wizard_cli.subprocess, "run", fake_run)
    installed, detail = setup_wizard_cli._install_ruflo()

    assert installed is True
    assert "completed" in detail.lower()
    assert calls[0][0] == ["npm", "install", "-g", "claude-flow@^3"]
    assert calls[0][1]["capture_output"] is True


def test_install_ruflo_fails_cleanly_without_npm(monkeypatch) -> None:
    monkeypatch.setattr(setup_wizard_cli.shutil, "which", lambda name: None)
    installed, detail = setup_wizard_cli._install_ruflo()
    assert installed is False
    assert "node.js 20+" in detail.lower()
