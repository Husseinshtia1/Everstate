from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .transfer_plan import RegisteredProject


@dataclass(frozen=True)
class ClaudeDesktopProject:
    project_id: str
    name: str
    folders: tuple[Path, ...]
    storage_path: Path
    account_id: str | None = None
    org_id: str | None = None
    metadata_only: bool = True


@dataclass(frozen=True)
class ClaudeDesktopAssociation:
    desktop_project: ClaudeDesktopProject
    status: str
    project: RegisteredProject | None
    candidates: tuple[RegisteredProject, ...]
    detail: str


def _desktop_roots(home: Path | None = None) -> tuple[Path, ...]:
    home = (home or Path.home()).expanduser()
    override = os.environ.get("EVERSTATE_CLAUDE_DESKTOP_ROOT")
    roots: list[Path] = []
    if override:
        roots.append(Path(override).expanduser())

    # Official Claude Desktop/Cowork storage locations. We probe all plausible
    # platform roots conservatively so tests and cross-platform copies work.
    roots.extend(
        [
            home / ".config" / "Claude" / "local-agent-mode-sessions",
            home / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions",
        ]
    )
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "Claude" / "local-agent-mode-sessions")

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return tuple(unique)


def _iter_spaces_files(home: Path | None = None) -> Iterable[Path]:
    for root in _desktop_roots(home):
        if not root.exists() or not root.is_dir():
            continue
        # Contract observed in current Claude Desktop/Cowork:
        # local-agent-mode-sessions/<accountId>/<orgId>/spaces.json
        try:
            account_dirs = [entry for entry in root.iterdir() if entry.is_dir()]
        except OSError:
            continue
        for account_dir in account_dirs:
            try:
                org_dirs = [entry for entry in account_dir.iterdir() if entry.is_dir()]
            except OSError:
                continue
            for org_dir in org_dirs:
                candidate = org_dir / "spaces.json"
                if candidate.is_file():
                    yield candidate


def _first_string(mapping: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_path_value(value: Any) -> list[Path]:
    found: list[Path] = []
    if isinstance(value, str) and value.strip():
        found.append(Path(value).expanduser())
    elif isinstance(value, dict):
        direct = _first_string(value, ("path", "folderPath", "folder_path", "rootPath", "root_path", "cwd"))
        if direct:
            found.append(Path(direct).expanduser())
        else:
            for nested in value.values():
                found.extend(_extract_path_value(nested))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_extract_path_value(nested))
    return found


def _extract_folders(space: dict[str, Any]) -> tuple[Path, ...]:
    values: list[Path] = []
    for key in (
        "folders",
        "folderAssignments",
        "folder_assignments",
        "folderPaths",
        "folder_paths",
        "directories",
        "roots",
        "localFolders",
        "local_folders",
    ):
        if key in space:
            values.extend(_extract_path_value(space[key]))

    # Some versions keep one root directly on the space object.
    direct = _first_string(space, ("folderPath", "folder_path", "rootPath", "root_path", "cwd"))
    if direct:
        values.append(Path(direct).expanduser())

    unique: list[Path] = []
    seen: set[str] = set()
    for value in values:
        try:
            normalized = value.resolve(strict=False)
        except OSError:
            normalized = value
        key = str(normalized)
        if key not in seen:
            seen.add(key)
            unique.append(normalized)
    return tuple(unique)


def _space_records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return [item for item in document if isinstance(item, dict)]
    if not isinstance(document, dict):
        return []

    for key in ("spaces", "projects", "items"):
        value = document.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            records: list[dict[str, Any]] = []
            for record_id, item in value.items():
                if not isinstance(item, dict):
                    continue
                copy = dict(item)
                copy.setdefault("id", str(record_id))
                records.append(copy)
            return records

    # Do not recursively inspect arbitrary renderer state: this adapter reads
    # only the bounded top-level project collection in spaces.json.
    return []


def _read_spaces_file(path: Path, *, max_bytes: int = 4 * 1024 * 1024) -> list[ClaudeDesktopProject]:
    try:
        if path.stat().st_size > max_bytes:
            return []
        document = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []

    try:
        org_id = path.parent.name or None
        account_id = path.parent.parent.name or None
    except IndexError:
        org_id = None
        account_id = None

    projects: list[ClaudeDesktopProject] = []
    for index, space in enumerate(_space_records(document), start=1):
        project_id = _first_string(space, ("id", "uuid", "spaceId", "space_id", "projectId", "project_id"))
        name = _first_string(space, ("name", "title", "displayName", "display_name"))
        if project_id is None:
            project_id = f"{path.parent.name}:space-{index}"
        if name is None:
            name = f"Unnamed Desktop project {index}"
        projects.append(
            ClaudeDesktopProject(
                project_id=project_id,
                name=name,
                folders=_extract_folders(space),
                storage_path=path,
                account_id=account_id,
                org_id=org_id,
            )
        )
    return projects


def discover_claude_desktop_projects(home: Path | None = None) -> list[ClaudeDesktopProject]:
    projects: list[ClaudeDesktopProject] = []
    seen: set[tuple[str, str]] = set()
    for path in _iter_spaces_files(home):
        for project in _read_spaces_file(path):
            key = (project.project_id, str(project.storage_path))
            if key not in seen:
                seen.add(key)
                projects.append(project)
    return sorted(projects, key=lambda item: (item.name.lower(), item.project_id))


def _contains(root: Path, child: Path) -> bool:
    try:
        child.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except (ValueError, OSError):
        return False


def associate_claude_desktop_project(
    desktop_project: ClaudeDesktopProject,
    registered_projects: Iterable[RegisteredProject],
) -> ClaudeDesktopAssociation:
    registered = list(registered_projects)
    if not desktop_project.folders:
        return ClaudeDesktopAssociation(
            desktop_project,
            "UNKNOWN",
            None,
            (),
            "Claude Desktop project metadata exposed no local folder assignment; Everstate will not guess.",
        )

    matches: dict[str, RegisteredProject] = {}
    evidence: list[str] = []
    for folder in desktop_project.folders:
        for project in registered:
            root = project.root_path
            try:
                exact = root.resolve(strict=False) == folder.resolve(strict=False)
            except OSError:
                exact = False
            if exact or _contains(root, folder) or _contains(folder, root):
                matches[project.project_id] = project
                evidence.append(f"{folder} ↔ {root}")

    candidates = tuple(sorted(matches.values(), key=lambda item: item.project_id))
    if len(candidates) == 1:
        return ClaudeDesktopAssociation(
            desktop_project,
            "VERIFIED",
            candidates[0],
            candidates,
            "Unique local-folder match: " + "; ".join(evidence),
        )
    if len(candidates) > 1:
        return ClaudeDesktopAssociation(
            desktop_project,
            "AMBIGUOUS",
            None,
            candidates,
            "Local folders match multiple canonical projects; Everstate will not guess.",
        )
    return ClaudeDesktopAssociation(
        desktop_project,
        "UNKNOWN",
        None,
        (),
        "No registered Everstate project matches the Claude Desktop project's local folders.",
    )
