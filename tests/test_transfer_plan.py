from pathlib import Path

import pytest

from everstate.storage import LocalStore
from everstate.transfer_plan import SourceEnvironment, build_transfer_plan, list_registered_projects


def store_with_projects(tmp_path: Path) -> LocalStore:
    store = LocalStore(tmp_path / "everstate.db")
    first = tmp_path / "alpha"
    second = tmp_path / "beta"
    first.mkdir()
    second.mkdir()
    store.upsert_project("proj_alpha", "alpha", first)
    store.upsert_project("proj_beta", "beta", second)
    return store


def test_registered_projects_are_listed(tmp_path: Path) -> None:
    store = store_with_projects(tmp_path)
    projects = list_registered_projects(store)
    assert {project.project_id for project in projects} == {"proj_alpha", "proj_beta"}


def test_transfer_never_assumes_all_projects(tmp_path: Path) -> None:
    store = store_with_projects(tmp_path)
    with pytest.raises(ValueError, match="never assumes all projects"):
        build_transfer_plan(
            store,
            source=SourceEnvironment.CLAUDE_DESKTOP,
            destination="gemini",
        )


def test_one_project_transfer_is_explicit(tmp_path: Path) -> None:
    store = store_with_projects(tmp_path)
    plan = build_transfer_plan(
        store,
        source=SourceEnvironment.CLAUDE_DESKTOP,
        destination="gemini",
        project_selectors=["proj_alpha"],
    )
    assert plan.scope == "single"
    assert [project.project_id for project in plan.projects] == ["proj_alpha"]
    assert plan.source is SourceEnvironment.CLAUDE_DESKTOP
    assert plan.destination == "gemini"


def test_selected_projects_are_supported(tmp_path: Path) -> None:
    store = store_with_projects(tmp_path)
    plan = build_transfer_plan(
        store,
        source=SourceEnvironment.CODEX,
        destination="claude-code",
        project_selectors=["proj_alpha", "proj_beta"],
    )
    assert plan.scope == "selected"
    assert len(plan.projects) == 2


def test_all_projects_requires_second_explicit_confirmation(tmp_path: Path) -> None:
    store = store_with_projects(tmp_path)
    with pytest.raises(ValueError, match="explicit confirmation"):
        build_transfer_plan(
            store,
            source=SourceEnvironment.CODEX,
            destination="gemini",
            all_projects=True,
        )

    plan = build_transfer_plan(
        store,
        source=SourceEnvironment.CODEX,
        destination="gemini",
        all_projects=True,
        confirm_all=True,
    )
    assert plan.scope == "all"
    assert len(plan.projects) == 2


def test_explicit_projects_and_all_are_mutually_exclusive(tmp_path: Path) -> None:
    store = store_with_projects(tmp_path)
    with pytest.raises(ValueError, match="not both"):
        build_transfer_plan(
            store,
            source=SourceEnvironment.CLAUDE_CODE,
            destination="codex",
            project_selectors=["proj_alpha"],
            all_projects=True,
            confirm_all=True,
        )
