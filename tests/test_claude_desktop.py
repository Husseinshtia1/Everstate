from __future__ import annotations

import json
from pathlib import Path

import everstate.claude_desktop as desktop
from everstate.claude_desktop import associate_claude_desktop_project, discover_claude_desktop_projects
from everstate.storage import LocalStore
from everstate.transfer_plan import RegisteredProject


def _spaces_file(home: Path, payload: object) -> Path:
    path = home / ".config" / "Claude" / "local-agent-mode-sessions" / "acct-1" / "org-1" / "spaces.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_discovers_actual_desktop_projects_from_spaces_json(tmp_path: Path) -> None:
    alpha = tmp_path / "alpha"
    beta = tmp_path / "beta"
    alpha.mkdir()
    beta.mkdir()
    _spaces_file(
        tmp_path,
        {
            "spaces": [
                {"id": "space-alpha", "name": "Alpha Desktop", "folderAssignments": [{"path": str(alpha)}]},
                {"spaceId": "space-beta", "title": "Beta Desktop", "folders": [str(beta)]},
            ]
        },
    )

    items = discover_claude_desktop_projects(tmp_path)

    assert [item.name for item in items] == ["Alpha Desktop", "Beta Desktop"]
    assert items[0].project_id == "space-alpha"
    assert items[0].folders == (alpha.resolve(),)
    assert items[1].project_id == "space-beta"
    assert items[1].folders == (beta.resolve(),)
    assert all(item.metadata_only for item in items)


def test_does_not_read_arbitrary_nested_renderer_state(tmp_path: Path) -> None:
    hidden = tmp_path / "hidden"
    hidden.mkdir()
    _spaces_file(tmp_path, {"renderer": {"spaces": [{"id": "wrong", "name": "Wrong", "folders": [str(hidden)]}]}})

    assert discover_claude_desktop_projects(tmp_path) == []


def test_unique_desktop_folder_to_canonical_project_is_verified(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    _spaces_file(tmp_path, {"spaces": [{"id": "space-1", "name": "Real Desktop Project", "folders": [str(root)]}]})
    desktop_project = discover_claude_desktop_projects(tmp_path)[0]
    canonical = RegisteredProject(project_id="proj_1", name="Canonical", root_path=root)

    association = associate_claude_desktop_project(desktop_project, [canonical])

    assert association.status == "VERIFIED"
    assert association.project == canonical


def test_desktop_project_without_folder_is_unknown(tmp_path: Path) -> None:
    _spaces_file(tmp_path, {"spaces": [{"id": "space-1", "name": "Cloud-only style project"}]})
    desktop_project = discover_claude_desktop_projects(tmp_path)[0]

    association = associate_claude_desktop_project(desktop_project, [])

    assert association.status == "UNKNOWN"
    assert association.project is None


def test_multiple_canonical_matches_are_ambiguous(tmp_path: Path) -> None:
    root = tmp_path / "project"
    nested = root / "nested"
    nested.mkdir(parents=True)
    _spaces_file(tmp_path, {"spaces": [{"id": "space-1", "name": "Desktop", "folders": [str(nested)]}]})
    desktop_project = discover_claude_desktop_projects(tmp_path)[0]
    projects = [
        RegisteredProject(project_id="proj_a", name="A", root_path=root),
        RegisteredProject(project_id="proj_b", name="B", root_path=nested),
    ]

    association = associate_claude_desktop_project(desktop_project, projects)

    assert association.status == "AMBIGUOUS"
    assert association.project is None
    assert {item.project_id for item in association.candidates} == {"proj_a", "proj_b"}


def test_spaces_file_size_is_bounded(tmp_path: Path) -> None:
    path = _spaces_file(tmp_path, {"spaces": []})
    path.write_text(" " * (4 * 1024 * 1024 + 1), encoding="utf-8")

    assert desktop._read_spaces_file(path) == []
