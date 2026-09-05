from __future__ import annotations

import everstate.claude_desktop_authorized as authorized


def test_invalid_project_id_never_attempts_navigation(monkeypatch) -> None:
    monkeypatch.setattr(authorized, "_opener", lambda: "/usr/bin/xdg-open")
    monkeypatch.setattr(authorized, "_query_scheme_handler", lambda: "claude.desktop")
    called = {"value": False}

    def fake_open(opener: str, url: str) -> int:
        called["value"] = True
        return 0

    monkeypatch.setattr(authorized, "_open_url", fake_open)
    result = authorized.open_claude_exact_project("not-a-project-id")
    assert result.valid_project_id is False
    assert result.attempted is False
    assert called["value"] is False


def test_exact_project_uuid_uses_documented_claude_deep_link(monkeypatch) -> None:
    project_id = "019c9c04-7ab0-719f-9153-e1a21ba5894f"
    monkeypatch.setattr(authorized, "_opener", lambda: "/usr/bin/xdg-open")
    monkeypatch.setattr(authorized, "_query_scheme_handler", lambda: "claude.desktop")
    seen = {}

    def fake_open(opener: str, url: str) -> int:
        seen["opener"] = opener
        seen["url"] = url
        return 0

    monkeypatch.setattr(authorized, "_open_url", fake_open)
    result = authorized.open_claude_exact_project(project_id)
    assert result.valid_project_id is True
    assert result.os_handoff_succeeded is True
    assert seen["url"] == f"claude://claude.ai/project/{project_id}"
