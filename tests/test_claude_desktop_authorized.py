from __future__ import annotations

from pathlib import Path

import everstate.claude_desktop_authorized as authorized


def test_probe_does_not_open_without_explicit_flag(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".config" / "Claude").mkdir(parents=True)
    monkeypatch.setattr(authorized.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(authorized, "_query_scheme_handler", lambda: "claude.desktop")
    monkeypatch.setattr(authorized, "_opener", lambda: "/usr/bin/xdg-open")
    monkeypatch.setattr(authorized, "_desktop_process_detected", lambda: True)

    item = authorized.probe_claude_desktop_authorized(open_projects=False)

    assert item.profile_exists is True
    assert item.can_attempt_ui_navigation is True
    assert item.navigation_attempted is False
    assert item.navigation_exit_code is None


def test_probe_opens_only_official_claude_deep_link(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".config" / "Claude").mkdir(parents=True)
    monkeypatch.setattr(authorized.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(authorized, "_query_scheme_handler", lambda: "claude.desktop")
    monkeypatch.setattr(authorized, "_opener", lambda: "/usr/bin/xdg-open")
    monkeypatch.setattr(authorized, "_desktop_process_detected", lambda: True)

    seen = {}

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        seen["command"] = command
        return Result()

    monkeypatch.setattr(authorized.subprocess, "run", fake_run)

    item = authorized.probe_claude_desktop_authorized(open_projects=True)

    assert item.navigation_attempted is True
    assert item.navigation_exit_code == 0
    assert seen["command"] == ["/usr/bin/xdg-open", "claude://claude.ai/project/invalid"]
