from __future__ import annotations

import subprocess
from pathlib import Path

from everstate.service import EverstateService
from everstate.storage import LocalStore


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_git_rewrite_refresh_preserves_semantic_truth(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "everstate@example.invalid")
    _git(root, "config", "user.name", "Everstate Test")
    (root / "app.txt").write_text("v1\n", encoding="utf-8")
    _git(root, "add", "app.txt")
    _git(root, "commit", "-m", "initial")

    service = EverstateService(LocalStore(tmp_path / "everstate.db"))
    service.set_objective(root, "Preserve objective across history rewrite")
    service.set_task(root, "Verify repository evidence")
    before = service.status(root)

    (root / "app.txt").write_text("v2\n", encoding="utf-8")
    _git(root, "add", "app.txt")
    _git(root, "commit", "-m", "second")
    _git(root, "reset", "--soft", "HEAD~1")
    _git(root, "commit", "-m", "rewritten-second")

    after = service.status(root)
    assert after.project_id == before.project_id
    assert after.version > before.version
    assert after.objective == "Preserve objective across history rewrite"
    assert after.current_task == "Verify repository evidence"


def test_dirty_worktree_refresh_does_not_erase_user_constraints(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "everstate@example.invalid")
    _git(root, "config", "user.name", "Everstate Test")
    (root / "config.txt").write_text("safe=true\n", encoding="utf-8")
    _git(root, "add", "config.txt")
    _git(root, "commit", "-m", "initial")

    service = EverstateService(LocalStore(tmp_path / "everstate.db"))
    service.add_constraint(root, "NO_CLOUD")
    service.set_next_action(root, "Review dirty diff")

    (root / "config.txt").write_text("safe=false\n", encoding="utf-8")
    state = service.status(root)

    assert state.active_constraints == ["NO_CLOUD"]
    assert state.next_action == "Review dirty diff"
    assert "config.txt" in state.modified_files
