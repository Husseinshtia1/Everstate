from __future__ import annotations

import subprocess
from pathlib import Path

from everstate.git_observer import snapshot, snapshot_event


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Everstate Test")
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "baseline")
    return root


def test_ruflo_runtime_tree_does_not_pollute_canonical_modified_files(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    before = snapshot_event("proj_test", root)

    runtime = root / ".claude-flow" / "tasks"
    runtime.mkdir(parents=True)
    (runtime / "store.json").write_text('{"tasks": []}\n', encoding="utf-8")

    snap = snapshot(root)
    after = snapshot_event("proj_test", root)

    assert snap.modified_files == []
    assert ".claude-flow" not in snap.status_porcelain
    assert after.content_hash == before.content_hash


def test_real_project_change_remains_visible_with_ruflo_runtime_noise(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    runtime = root / ".claude-flow" / "agents"
    runtime.mkdir(parents=True)
    (runtime / "store.json").write_text('{"agents": {}}\n', encoding="utf-8")
    (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")

    snap = snapshot(root)

    assert snap.modified_files == ["app.py"]
    assert "app.py" in snap.status_porcelain
    assert ".claude-flow" not in snap.status_porcelain
