from __future__ import annotations

import subprocess
from pathlib import Path

from everstate.service import EverstateService
from everstate.storage import LocalStore


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Everstate Test")
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "initial")
    return root


def test_init_materializes_first_state(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    service = EverstateService(LocalStore(tmp_path / "state.db"))

    project_id = service.init_project(root)
    state = service.status(root)

    assert project_id.startswith("proj_")
    assert state.project_id == project_id
    assert state.version == 1
    assert state.modified_files == []


def test_git_change_creates_new_state_version(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    service = EverstateService(LocalStore(tmp_path / "state.db"))
    service.init_project(root)

    (root / "app.py").write_text("print('hi')\n", encoding="utf-8")
    state = service.status(root)

    assert state.version == 2
    assert "app.py" in state.modified_files


def test_unchanged_repo_does_not_create_extra_version(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    service = EverstateService(LocalStore(tmp_path / "state.db"))
    service.init_project(root)

    first = service.status(root)
    second = service.status(root)

    assert first.version == second.version == 1


def test_resume_reports_working_tree_change(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    service = EverstateService(LocalStore(tmp_path / "state.db"))
    service.init_project(root)
    (root / "feature.py").write_text("x = 1\n", encoding="utf-8")

    brief = service.resume_text(root)

    assert "EVERSTATE PROJECT RESUME" in brief
    assert "feature.py" in brief
    assert "None captured yet" in brief
