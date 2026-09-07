from __future__ import annotations

from pathlib import Path

from everstate import cli as legacy_cli
from everstate import cli_runtime


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
