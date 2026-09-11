from __future__ import annotations

from everstate.providers import PROVIDERS


def test_codex_automation_uses_workspace_write_without_legacy_fallback(monkeypatch):
    monkeypatch.delenv("EVERSTATE_CODEX_LEGACY_LANDLOCK", raising=False)

    command = PROVIDERS["codex"].automation_command("do work")

    assert "--sandbox" in command
    assert "workspace-write" in command
    assert "danger-full-access" not in command
    assert "use_legacy_landlock=true" not in command


def test_codex_automation_can_use_legacy_landlock_without_disabling_sandbox(monkeypatch):
    monkeypatch.setenv("EVERSTATE_CODEX_LEGACY_LANDLOCK", "1")

    command = PROVIDERS["codex"].automation_command("do work")

    assert command[1:3] == ["-c", "use_legacy_landlock=true"]
    assert "--sandbox" in command
    assert "workspace-write" in command
    assert "danger-full-access" not in command
    assert 'approval_policy="never"' in command
