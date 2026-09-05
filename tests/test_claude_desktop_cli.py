from __future__ import annotations

from typer.testing import CliRunner

import everstate.claude_desktop_cli as desktop_cli
from everstate.claude_desktop_cli import app

runner = CliRunner()


def test_projects_is_a_real_subcommand(monkeypatch) -> None:
    monkeypatch.setattr(desktop_cli, "discover_claude_desktop_projects", lambda: [])
    monkeypatch.setattr(desktop_cli, "list_registered_projects", lambda store: [])

    result = runner.invoke(app, ["projects", "--full-paths"])

    assert result.exit_code == 0
    assert "Claude Desktop local Cowork projects" in result.stdout
    assert "No local Claude Desktop/Cowork projects were found" in result.stdout
    assert "cloud Projects are a separate source surface" in result.stdout
    assert "Got unexpected extra argument" not in result.stdout


def test_help_lists_projects_and_diagnose_subcommands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "projects" in result.stdout
    assert "diagnose" in result.stdout
