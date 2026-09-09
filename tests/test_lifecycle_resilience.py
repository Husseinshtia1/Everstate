from __future__ import annotations

import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from everstate.service import EverstateService
from everstate.storage import LocalStore


def _service(db_path: Path) -> EverstateService:
    return EverstateService(LocalStore(db_path))


def test_process_restart_reopens_same_canonical_state(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    db = tmp_path / "everstate.db"

    first = _service(db)
    first.set_objective(root, "Ship safely")
    first.set_task(root, "Finish migration")
    first.add_constraint(root, "NO_CLOUD")
    first.set_next_action(root, "Run acceptance suite")
    before = first.status(root)

    restarted = _service(db)
    after = restarted.status(root)

    assert after.project_id == before.project_id
    assert after.version == before.version
    assert after.objective == "Ship safely"
    assert after.current_task == "Finish migration"
    assert after.active_constraints == ["NO_CLOUD"]
    assert after.next_action == "Run acceptance suite"


def test_real_directory_relocation_preserves_project_identity_and_state(tmp_path: Path) -> None:
    original = tmp_path / "old-location"
    original.mkdir()
    db = tmp_path / "everstate.db"
    service = _service(db)

    service.set_objective(original, "Keep identity across move")
    service.add_decision(original, "Use immutable project marker")
    before = service.status(original)

    moved = tmp_path / "new location with spaces"
    original.rename(moved)

    after = service.status(moved)
    assert after.project_id == before.project_id
    assert after.objective == before.objective
    assert after.decisions == before.decisions
    project = service.store.get_project(before.project_id)
    assert project is not None
    assert Path(project["root_path"]).resolve() == moved.resolve()


def test_copy_does_not_hijack_live_original_project_identity(tmp_path: Path) -> None:
    original = tmp_path / "original"
    original.mkdir()
    db = tmp_path / "everstate.db"
    service = _service(db)
    service.set_task(original, "Original task")
    original_state = service.status(original)

    copied = tmp_path / "copied"
    shutil.copytree(original, copied)
    copied_state = service.status(copied)

    assert copied_state.project_id != original_state.project_id
    assert service.status(original).project_id == original_state.project_id
    assert service.status(original).current_task == "Original task"


def test_corrupt_identity_marker_is_ignored_fail_safe(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    (root / ".everstate").mkdir(parents=True)
    (root / ".everstate" / "project.json").write_text("{broken", encoding="utf-8")

    service = _service(tmp_path / "everstate.db")
    project_id = service.init_project(root)

    assert project_id.startswith("proj_")
    marker = json.loads((root / ".everstate" / "project.json").read_text(encoding="utf-8"))
    assert marker["project_id"] == project_id


def test_concurrent_agents_preserve_all_distinct_decisions(tmp_path: Path) -> None:
    root = tmp_path / "shared-project"
    root.mkdir()
    db = tmp_path / "everstate.db"
    service = _service(db)
    service.init_project(root)
    decisions = [f"decision-{index}" for index in range(12)]

    def write(value: str) -> None:
        worker = _service(db)
        worker.add_decision(root, value)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(write, decisions))

    state = _service(db).status(root)
    assert set(state.decisions) == set(decisions)
    assert len(state.decisions) == len(decisions)


def test_corrupt_newest_state_falls_back_then_recovers_with_higher_version(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    db = tmp_path / "everstate.db"
    service = _service(db)
    service.set_objective(root, "Recover canonical state")
    healthy = service.set_task(root, "Before corruption")
    corrupt_version = healthy.version + 1

    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO state_versions(project_id, version, state_json) VALUES (?, ?, ?)",
            (healthy.project_id, corrupt_version, "{not-valid-json"),
        )
        conn.commit()

    recovered = _service(db).status(root)
    assert recovered.version == healthy.version
    assert recovered.objective == "Recover canonical state"
    assert recovered.current_task == "Before corruption"

    repaired = _service(db).set_next_action(root, "Continue from last valid snapshot")
    assert repaired.version > corrupt_version
    assert repaired.next_action == "Continue from last valid snapshot"
    assert repaired.objective == "Recover canonical state"


def test_sqlite_busy_timeout_is_configured_for_contention(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "everstate.db")
    with store.connect() as conn:
        timeout_ms = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout_ms >= 30_000
