from __future__ import annotations

import subprocess
from pathlib import Path

from everstate.project_onboarding import (
    ProjectCandidate,
    ProjectCandidateKind,
    ProjectCandidateRole,
    classify_candidate_role,
    classify_family_role,
    register_explicit_project_path,
)
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


def _candidate(path: Path, role: ProjectCandidateRole) -> ProjectCandidate:
    return ProjectCandidate(
        root_path=path,
        suggested_name=path.name,
        session_count=1,
        sources=(SourceEnvironment.CLAUDE_CODE,),
        already_registered=False,
        project_id="proj_test",
        kind=ProjectCandidateKind.WORKSPACE_PROJECT,
        role=role,
    )


def test_git_root_is_primary_project(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "product")
    assert classify_candidate_role(repo, ProjectCandidateKind.GIT_PROJECT) is ProjectCandidateRole.PRIMARY_PROJECT


def test_agent_workspace_is_run_artifact(tmp_path: Path) -> None:
    path = tmp_path / "agent_b14_upload_final"
    path.mkdir()
    assert classify_candidate_role(path, ProjectCandidateKind.WORKSPACE_PROJECT) is ProjectCandidateRole.RUN_ARTIFACT


def test_acceptance_family_is_experiment_family(tmp_path: Path) -> None:
    root = tmp_path / "ayneye_external_mcp_acceptance"
    root.mkdir()
    members = (
        _candidate(root / "agent_a", ProjectCandidateRole.RUN_ARTIFACT),
        _candidate(root / "agent_b", ProjectCandidateRole.RUN_ARTIFACT),
    )
    assert classify_family_role(root, members) is ProjectCandidateRole.EXPERIMENT_FAMILY


def test_unknown_workspace_is_not_promoted_to_primary(tmp_path: Path) -> None:
    path = tmp_path / "openmotion"
    path.mkdir()
    assert classify_candidate_role(path, ProjectCandidateKind.WORKSPACE_PROJECT) is ProjectCandidateRole.UNKNOWN


def test_explicit_path_registration_uses_user_name_and_initial_state(tmp_path: Path) -> None:
    root = tmp_path / "known-project-root"
    root.mkdir()
    store = LocalStore(tmp_path / "everstate.db")

    project = register_explicit_project_path(store, root, "Ayneye")

    registered = list_registered_projects(store)
    assert len(registered) == 1
    assert registered[0].project_id == project.project_id
    assert registered[0].name == "Ayneye"
    state = store.latest_state(project.project_id)
    assert state is not None
    assert state.version == 1
