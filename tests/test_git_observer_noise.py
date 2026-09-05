from __future__ import annotations

import subprocess
from pathlib import Path

from everstate.git_observer import snapshot


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "everstate-test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Everstate Test"], cwd=root, check=True)
    (root / "tracked.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True, text=True)


def test_snapshot_ignores_internal_and_generated_noise(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "tracked.cpython-312.pyc").write_bytes(b"generated")
    (tmp_path / ".everstate" / "handoffs").mkdir(parents=True)
    (tmp_path / ".everstate" / "handoffs" / "state-v1-codex.md").write_text("handoff", encoding="utf-8")

    snap = snapshot(tmp_path)

    assert snap.modified_files == []
    assert "__pycache__" not in snap.status_porcelain
    assert ".everstate/" not in snap.status_porcelain


def test_snapshot_keeps_real_untracked_files(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "real_change.py").write_text("print('change')\n", encoding="utf-8")

    snap = snapshot(tmp_path)

    assert snap.modified_files == ["real_change.py"]
