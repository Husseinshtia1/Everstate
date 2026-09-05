from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import everstate.transfer_cli as transfer_cli
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


def test_non_interactive_mode_never_guesses_missing_source(monkeypatch, tmp_path: Path) -> None:
    store = _store_with_projects(tmp_path)
    monkeypatch.setattr(transfer_cli, "_store", lambda: store)

    result = runner.invoke(
        app,
        ["--project", "proj_1", "--to", "gemini", "--non-interactive"],
    )

    assert result.exit_code != 0
    assert "--from is required" in result.stdout


def test_non_interactive_mode_never_guesses_project(monkeypatch, tmp_path: Path) -> None:
    store = _store_with_projects(tmp_path)
    monkeypatch.setattr(transfer_cli, "_store", lambda: store)

    result = runner.invoke(
        app,
        ["--from", "codex", "--to", "gemini", "--non-interactive"],
    )

    assert result.exit_code != 0
    assert "Select --session, at least one --project, or --all" in result.stdout


def test_wizard_all_projects_requires_second_confirmation(monkeypatch, tmp_path: Path) -> None:
    store = _store_with_projects(tmp_path, count=2)
    monkeypatch.setattr(transfer_cli, "_store", lambda: store)

    # current-worktree -> scope all -> confirm -> destination auto
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
    assert "Bulk transfer selection cancelled" in result.stdout
