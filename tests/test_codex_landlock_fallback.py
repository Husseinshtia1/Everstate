from __future__ import annotations

from types import SimpleNamespace

from everstate.providers import PROVIDERS, ProviderAdapter


def test_codex_automation_stays_on_workspace_write_managed_sandbox(monkeypatch):
    monkeypatch.setenv("EVERSTATE_CODEX_LEGACY_LANDLOCK", "1")

    command = PROVIDERS["codex"].automation_command("do work")

    assert "--sandbox" in command
    assert "workspace-write" in command
    assert "danger-full-access" not in command
    assert "use_legacy_landlock=true" not in command
    assert 'approval_policy="never"' in command


def test_codex_preflight_probes_managed_sandbox_without_inference(monkeypatch):
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/usr/bin/codex")
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        if command[1:] == ["login", "status"]:
            return SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("everstate.providers.subprocess.run", fake_run)

    ready, detail = PROVIDERS["codex"].automation_preflight()

    assert ready is True
    assert "managed sandbox probe passed" in detail
    assert calls[1] == ["/usr/bin/codex", "sandbox", "/bin/true"]


def test_codex_preflight_explains_ubuntu_userns_failure(monkeypatch):
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/usr/bin/codex")

    def fake_run(command, **kwargs):
        if command[1:] == ["login", "status"]:
            return SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT", stderr="")
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted",
        )

    monkeypatch.setattr("everstate.providers.subprocess.run", fake_run)

    ready, detail = PROVIDERS["codex"].automation_preflight()

    assert ready is False
    assert "managed workspace sandbox is not usable" in detail
    assert "Ubuntu/AppArmor" in detail
    assert "do not use legacy Landlock" in detail
