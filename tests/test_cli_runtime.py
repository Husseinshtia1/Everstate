from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from everstate import cli as legacy_cli
from everstate import cli_runtime
from everstate.service import EverstateService
from everstate.storage import LocalStore


def test_cli_runtime_honors_everstate_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EVERSTATE_HOME", str(tmp_path))

    expected = tmp_path.resolve() / ".everstate" / "everstate.db"
    assert cli_runtime.runtime_db_path() == expected
    assert legacy_cli._db_path() == expected


def test_cli_runtime_defaults_to_user_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EVERSTATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    # Path.home() respects HOME on the supported POSIX runtime used by Everstate.
    expected = Path.home().resolve() / ".everstate" / "everstate.db"
    assert cli_runtime.runtime_db_path() == expected


def test_start_dry_run_persists_checkpoint_without_launch(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("EVERSTATE_HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(
        cli_runtime.app,
        [
            "start",
            "CLI_START_TASK",
            "--path",
            str(project),
            "--target",
            "codex",
            "--objective",
            "CLI_START_OBJECTIVE",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Checkpoint persisted before provider launch" in result.output
    assert "Dry run only; no provider process was launched" in result.output

    service = EverstateService(LocalStore(home / ".everstate" / "everstate.db"))
    state = service.status(project)
    assert state.objective == "CLI_START_OBJECTIVE"
    assert state.current_task == "CLI_START_TASK"
    assert state.next_action == "Continue current task in codex: CLI_START_TASK"
