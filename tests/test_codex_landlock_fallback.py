from __future__ import annotations

from types import SimpleNamespace

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


def test_codex_landlock_preflight_runs_command_directly_after_sandbox(monkeypatch):
    monkeypatch.setenv("EVERSTATE_CODEX_LEGACY_LANDLOCK", "1")
    monkeypatch.setattr(PROVIDERS["codex"], "resolve_executable", lambda: "/usr/bin/codex")
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        if command[1:] == ["login", "status"]:
            return SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("everstate.providers.subprocess.run", fake_run)

    ready, detail = PROVIDERS["codex"].automation_preflight()

    assert ready is True
    assert "legacy Landlock sandbox probe passed" in detail
    assert calls[1] == [
        "/usr/bin/codex",
        "-c",
        "use_legacy_landlock=true",
        "sandbox",
        "/bin/true",
    ]
    assert "linux" not in calls[1]
