from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import everstate.project_onboarding as onboarding
from everstate.project_onboarding import (
    ProjectCandidateKind,
    discover_project_candidates,
    discover_workspace_families,
    register_project_candidate,
    register_workspace_family,
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


def test_workspace_family_groups_sibling_workdirs_without_changing_candidates(monkeypatch, tmp_path: Path) -> None:
    parent = tmp_path / "ayneye_external"
    a = parent / "agent_a"
    b = parent / "agent_b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    store = LocalStore(tmp_path / "everstate.db")
    sessions = [
        _session(SourceEnvironment.CLAUDE_CODE, "a1", a),
        _session(SourceEnvironment.CLAUDE_CODE, "a2", a),
        _session(SourceEnvironment.CLAUDE_CODE, "b1", b),
    ]
    monkeypatch.setattr(onboarding, "discover_sessions", lambda source: sessions)

    candidates = discover_project_candidates(store, sources=(SourceEnvironment.CLAUDE_CODE,))
    families = discover_workspace_families(store, candidates)

    assert {item.root_path for item in candidates} == {a.resolve(), b.resolve()}
    assert len(families) == 1
    assert families[0].root_path == parent.resolve()
    assert len(families[0].members) == 2
    assert families[0].session_count == 3


def test_workspace_family_never_uses_home_or_downloads_as_root(monkeypatch, tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "everstate.db")
    # Patch unsafe-root logic deterministically instead of depending on the CI home path.
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    sessions = [
        _session(SourceEnvironment.CLAUDE_CODE, "a", left),
        _session(SourceEnvironment.CLAUDE_CODE, "b", right),
    ]
    monkeypatch.setattr(onboarding, "discover_sessions", lambda source: sessions)
    monkeypatch.setattr(onboarding, "_unsafe_family_root", lambda path: path.resolve() == tmp_path.resolve())

    candidates = discover_project_candidates(store, sources=(SourceEnvironment.CLAUDE_CODE,))

    assert discover_workspace_families(store, candidates) == []


def test_register_workspace_family_creates_one_canonical_project(monkeypatch, tmp_path: Path) -> None:
    parent = tmp_path / "family"
    a = parent / "agent_a"
    b = parent / "agent_b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    store = LocalStore(tmp_path / "everstate.db")
    sessions = [
        _session(SourceEnvironment.CLAUDE_CODE, "a", a),
        _session(SourceEnvironment.CLAUDE_CODE, "b", b),
    ]
    monkeypatch.setattr(onboarding, "discover_sessions", lambda source: sessions)
    candidates = discover_project_candidates(store, sources=(SourceEnvironment.CLAUDE_CODE,))
    family = discover_workspace_families(store, candidates)[0]

    registered = register_workspace_family(store, family)

    projects = list_registered_projects(store)
    assert len(projects) == 1
    assert registered.root_path == parent.resolve()
    assert projects[0].root_path == parent.resolve()
    assert store.latest_state(registered.project_id).version == 1


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
