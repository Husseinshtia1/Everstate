from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import everstate.transfer_cli as transfer_cli
from everstate.claude_desktop import ClaudeDesktopProject
from everstate.storage import LocalStore
from everstate.transfer_cli import app

runner = CliRunner()


def _store_with_projects(tmp_path: Path, count: int = 1) -> LocalStore:
    store = LocalStore(tmp_path / "everstate.db")
    for index in range(1, count + 1):
        root = tmp_path / f"project-{index}"
        root.mkdir()
        store.upsert_project(f"proj_{index}", f"Project {index}", root)
    return store


def test_wizard_asks_source_project_and_destination(monkeypatch, tmp_path: Path) -> None:
    store = _store_with_projects(tmp_path)
    monkeypatch.setattr(transfer_cli, "_store", lambda: store)

    result = runner.invoke(app, input="1\n1\n1\n1\n")

    assert result.exit_code == 0
    assert "Where are you continuing from?" in result.stdout
    assert "Which project scope do you want?" in result.stdout
    assert "Where do you want to continue?" in result.stdout
    assert "SOURCE: current-worktree" in result.stdout
    assert "PROJECT COUNT: 1" in result.stdout
    assert "DESTINATION: auto" in result.stdout
    assert "Planning only" in result.stdout


def test_claude_desktop_source_uses_actual_desktop_inventory(monkeypatch, tmp_path: Path) -> None:
    store = _store_with_projects(tmp_path)
    canonical_root = tmp_path / "project-1"
    desktop_project = ClaudeDesktopProject(
        project_id="desktop-space-1",
        name="Actual Desktop Project",
        folders=(canonical_root.resolve(),),
        storage_path=tmp_path / "spaces.json",
    )
    monkeypatch.setattr(transfer_cli, "_store", lambda: store)
    monkeypatch.setattr(transfer_cli, "discover_claude_desktop_projects", lambda: [desktop_project])

    # Source 2 = claude-desktop, Desktop project 1, destination 1 = auto.
    result = runner.invoke(app, input="2\n1\n1\n")

    assert result.exit_code == 0
    assert "Claude Desktop projects — actual source inventory" in result.stdout
    assert "Actual Desktop Project" in result.stdout
    assert "Verified canonical mapping" in result.stdout
    assert "SOURCE: claude-desktop" in result.stdout
    assert "PROJECT COUNT: 1" in result.stdout
    assert "Project 1" in result.stdout
    assert "Everstate registered projects" not in result.stdout


def test_claude_desktop_without_inventory_does_not_fallback_to_registry(monkeypatch, tmp_path: Path) -> None:
    store = _store_with_projects(tmp_path)
    monkeypatch.setattr(transfer_cli, "_store", lambda: store)
    monkeypatch.setattr(transfer_cli, "discover_claude_desktop_projects", lambda: [])

    result = runner.invoke(app, input="2\n")

    assert result.exit_code != 0
    assert "No local Claude Desktop/Cowork projects were found" in result.output
    assert "will not substitute Claude Code sessions or registered projects" in result.output


def test_projects_subcommand_bypasses_interactive_wizard(monkeypatch, tmp_path: Path) -> None:
    store = _store_with_projects(tmp_path)
    monkeypatch.setattr(transfer_cli, "_store", lambda: store)

    result = runner.invoke(app, ["projects"])

    assert result.exit_code == 0
    assert "Everstate registered projects" in result.stdout
    assert "Project 1" in result.stdout
    assert "Where are you continuing from?" not in result.stdout
    assert "Source number" not in result.stdout


def test_non_interactive_mode_never_guesses_missing_source(monkeypatch, tmp_path: Path) -> None:
    store = _store_with_projects(tmp_path)
    monkeypatch.setattr(transfer_cli, "_store", lambda: store)

    result = runner.invoke(
        app,
        ["--project", "proj_1", "--to", "gemini", "--non-interactive"],
    )

    assert result.exit_code != 0


def test_non_interactive_mode_never_guesses_project(monkeypatch, tmp_path: Path) -> None:
    store = _store_with_projects(tmp_path)
    monkeypatch.setattr(transfer_cli, "_store", lambda: store)

    result = runner.invoke(
        app,
        ["--from", "codex", "--to", "gemini", "--non-interactive"],
    )

    assert result.exit_code != 0


def test_wizard_all_projects_requires_second_confirmation(monkeypatch, tmp_path: Path) -> None:
    store = _store_with_projects(tmp_path, count=2)
    monkeypatch.setattr(transfer_cli, "_store", lambda: store)

    result = runner.invoke(app, input="1\n3\ny\n1\n")

    assert result.exit_code == 0
    assert "You selected ALL 2 registered projects" in result.stdout
    assert "SCOPE: all" in result.stdout
    assert "PROJECT COUNT: 2" in result.stdout


def test_wizard_cancelled_all_projects_does_not_build_plan(monkeypatch, tmp_path: Path) -> None:
    store = _store_with_projects(tmp_path, count=2)
    monkeypatch.setattr(transfer_cli, "_store", lambda: store)

    result = runner.invoke(app, input="1\n3\nn\n")

    assert result.exit_code != 0
    assert "You selected ALL 2 registered projects" in result.stdout
