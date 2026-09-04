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


def test_explicit_state_capture_is_versioned_and_persistent(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    store = LocalStore(tmp_path / "state.db")
    service = EverstateService(store)
    service.init_project(root)

    service.set_objective(root, "Ship the continuity prototype")
    service.set_task(root, "Implement structured state capture")
    service.add_decision(root, "Local-first is the default")
    service.add_constraint(root, "Do not require a cloud account")
    service.add_failure(root, "Transcript-only handoff loses current-state semantics")
    service.add_blocker(root, "Claude/Codex adapters are not implemented yet")
    state = service.set_next_action(root, "Build the first continuation packet")

    assert state.objective == "Ship the continuity prototype"
    assert state.current_task == "Implement structured state capture"
    assert state.decisions == ["Local-first is the default"]
    assert state.active_constraints == ["Do not require a cloud account"]
    assert state.failed_attempts == ["Transcript-only handoff loses current-state semantics"]
    assert state.blockers == ["Claude/Codex adapters are not implemented yet"]
    assert state.next_action == "Build the first continuation packet"
    assert state.version == 8

    latest = store.latest_state(state.project_id)
    assert latest is not None
    assert latest.model_dump() == state.model_dump()


def test_duplicate_list_state_is_not_duplicated(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    service = EverstateService(LocalStore(tmp_path / "state.db"))
    service.init_project(root)

    service.add_constraint(root, "No cloud dependency")
    state = service.add_constraint(root, "No cloud dependency")

    assert state.active_constraints == ["No cloud dependency"]


def test_explicit_state_capture_is_stored_as_events(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    store = LocalStore(tmp_path / "state.db")
    service = EverstateService(store)
    project_id = service.init_project(root)

    service.add_decision(root, "Use SQLite for the local prototype")

    events = store.list_events(project_id)
    assert any(row["event_type"] == "decision_added" for row in events)
    assert any(row["source_type"] == "explicit_user_input" for row in events)


def test_resume_reports_structured_continuity_state(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    service = EverstateService(LocalStore(tmp_path / "state.db"))
    service.init_project(root)
    service.set_objective(root, "Prove cross-AI continuity")
    service.set_task(root, "Build M1")
    service.add_decision(root, "Use local-first state")
    service.add_constraint(root, "Do not upload raw source code")
    service.add_failure(root, "Raw transcript dumping produced noisy context")
    service.add_blocker(root, "No provider adapter yet")
    service.set_next_action(root, "Implement continuation packet")
    (root / "feature.py").write_text("x = 1\n", encoding="utf-8")

    brief = service.resume_text(root)

    assert "EVERSTATE PROJECT RESUME" in brief
    assert "Prove cross-AI continuity" in brief
    assert "Build M1" in brief
    assert "Use local-first state" in brief
    assert "Do not upload raw source code" in brief
    assert "Raw transcript dumping produced noisy context" in brief
    assert "No provider adapter yet" in brief
    assert "Implement continuation packet" in brief
    assert "feature.py" in brief


def test_continuation_packet_is_ai_ready_and_version_pinned(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    service = EverstateService(LocalStore(tmp_path / "state.db"))
    service.init_project(root)
    service.set_objective(root, "Complete authentication migration")
    service.set_task(root, "Fix OAuth callback regression")
    service.add_decision(root, "Provider B remains active")
    service.add_constraint(root, "Do not modify database schema")
    service.add_failure(root, "Provider A fallback duplicated callback handling")
    service.add_blocker(root, "Redirect URI test is failing")
    service.set_next_action(root, "Run the failing callback test in isolation")
    (root / "auth.py").write_text("provider = 'B'\n", encoding="utf-8")

    packet = service.continuation_packet(root)
    prompt = packet.to_prompt()

    assert packet.state_version == service.status(root).version
    assert "auth.py" in packet.modified_files
    assert "EVERSTATE CONTINUATION PACKET" in prompt
    assert "Do not repeat FAILED ATTEMPTS" in prompt
    assert "Provider B remains active" in prompt
    assert "Do not modify database schema" in prompt
    assert "Provider A fallback duplicated callback handling" in prompt
    assert "Run the failing callback test in isolation" in prompt
