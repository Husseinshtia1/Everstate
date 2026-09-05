from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import everstate.project_onboarding as onboarding
from everstate.project_onboarding import (
    ProjectCandidateKind,
    discover_project_candidates,
    register_project_candidate,
)
from everstate.service import EverstateService
from everstate.source_discovery import DiscoveredSession
from everstate.storage import LocalStore
from everstate.transfer_plan import SourceEnvironment, list_registered_projects


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Everstate Test"], cwd=path, check=True)
    (path / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True, text=True)
    return path


def _session(source: SourceEnvironment, session_id: str, cwd: Path) -> DiscoveredSession:
    return DiscoveredSession(
        source=source,
        session_id=session_id,
        storage_path=cwd / f"{session_id}.jsonl",
        working_directory=cwd,
        updated_at=datetime.now(timezone.utc),
    )


def test_discovery_collapses_nested_sessions_to_git_toplevel(monkeypatch, tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "project")
    nested = repo / "src" / "feature"
    nested.mkdir(parents=True)
    store = LocalStore(tmp_path / "everstate.db")

    sessions = [
        _session(SourceEnvironment.CLAUDE_CODE, "a", nested),
        _session(SourceEnvironment.CLAUDE_CODE, "b", repo),
    ]
    monkeypatch.setattr(onboarding, "discover_sessions", lambda source: sessions)

    items = discover_project_candidates(store, sources=(SourceEnvironment.CLAUDE_CODE,))

    assert len(items) == 1
    assert items[0].root_path == repo.resolve()
    assert items[0].session_count == 2
    assert items[0].already_registered is False
    assert items[0].kind is ProjectCandidateKind.GIT_PROJECT


def test_non_git_workdir_is_proposed_as_workspace(monkeypatch, tmp_path: Path) -> None:
    workdir = tmp_path / "not-git"
    workdir.mkdir()
    store = LocalStore(tmp_path / "everstate.db")
    monkeypatch.setattr(
        onboarding,
        "discover_sessions",
        lambda source: [_session(SourceEnvironment.CLAUDE_CODE, "a", workdir)],
    )

    items = discover_project_candidates(store, sources=(SourceEnvironment.CLAUDE_CODE,))

    assert len(items) == 1
    assert items[0].root_path == workdir.resolve()
    assert items[0].kind is ProjectCandidateKind.WORKSPACE_PROJECT


def test_workspace_sessions_with_same_workdir_are_grouped(monkeypatch, tmp_path: Path) -> None:
    workdir = tmp_path / "workspace"
    workdir.mkdir()
    store = LocalStore(tmp_path / "everstate.db")
    sessions = [
        _session(SourceEnvironment.CLAUDE_CODE, "a", workdir),
        _session(SourceEnvironment.CLAUDE_CODE, "b", workdir),
    ]
    monkeypatch.setattr(onboarding, "discover_sessions", lambda source: sessions)

    items = discover_project_candidates(store, sources=(SourceEnvironment.CLAUDE_CODE,))

    assert len(items) == 1
    assert items[0].session_count == 2
    assert items[0].kind is ProjectCandidateKind.WORKSPACE_PROJECT


def test_register_git_candidate_uses_canonical_project_id_and_initial_state(monkeypatch, tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "project")
    store = LocalStore(tmp_path / "everstate.db")
    monkeypatch.setattr(
        onboarding,
        "discover_sessions",
        lambda source: [_session(SourceEnvironment.CODEX, "a", repo)],
    )
    candidate = discover_project_candidates(store, sources=(SourceEnvironment.CODEX,))[0]

    registered = register_project_candidate(store, candidate)

    projects = list_registered_projects(store)
    assert len(projects) == 1
    assert registered.project_id == candidate.project_id == projects[0].project_id
    assert store.latest_state(registered.project_id) is not None
    assert store.latest_state(registered.project_id).version == 1


def test_register_workspace_candidate_creates_state_and_status_works(monkeypatch, tmp_path: Path) -> None:
    workdir = tmp_path / "workspace"
    workdir.mkdir()
    store = LocalStore(tmp_path / "everstate.db")
    monkeypatch.setattr(
        onboarding,
        "discover_sessions",
        lambda source: [_session(SourceEnvironment.CLAUDE_CODE, "a", workdir)],
    )
    candidate = discover_project_candidates(store, sources=(SourceEnvironment.CLAUDE_CODE,))[0]

    registered = register_project_candidate(store, candidate)
    state = EverstateService(store).status(workdir)

    assert registered.project_id == candidate.project_id
    assert state.version == 1
    assert state.project_id == registered.project_id
    assert state.modified_files == []


def test_workspace_explicit_state_updates_continue_without_git(monkeypatch, tmp_path: Path) -> None:
    workdir = tmp_path / "workspace"
    workdir.mkdir()
    store = LocalStore(tmp_path / "everstate.db")
    service = EverstateService(store)
    service.init_project(workdir)

    state = service.set_task(workdir, "Continue workspace task")

    assert state.version == 2
    assert service.status(workdir).current_task == "Continue workspace task"
    assert "Continue workspace task" in service.continuation_text(workdir)


def test_registered_candidate_is_reported_not_duplicated(monkeypatch, tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "project")
    store = LocalStore(tmp_path / "everstate.db")
    sessions = [_session(SourceEnvironment.CODEX, "a", repo)]
    monkeypatch.setattr(onboarding, "discover_sessions", lambda source: sessions)

    first = discover_project_candidates(store, sources=(SourceEnvironment.CODEX,))[0]
    register_project_candidate(store, first)
    second = discover_project_candidates(store, sources=(SourceEnvironment.CODEX,))[0]

    assert second.already_registered is True
    assert second.project_id == first.project_id
