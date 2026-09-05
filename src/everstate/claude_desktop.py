from __future__ import annotations

import json
import os
import re
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


@dataclass(frozen=True)
class ClaudeDesktopProfileDiagnosis:
    profile_root: Path
    exists: bool
    local_agent_root_exists: bool
    spaces_file_count: int
    claude_ai_indexeddb_exists: bool
    claude_ai_local_storage_exists: bool
    cookies_store_exists: bool

    @property
    def has_local_cowork_inventory(self) -> bool:
        return self.spaces_file_count > 0

    @property
    def has_cloud_renderer_profile(self) -> bool:
        return self.claude_ai_indexeddb_exists or self.claude_ai_local_storage_exists


@dataclass(frozen=True)
class ClaudeCloudCacheProbe:
    profile_root: Path
    indexeddb_root: Path
    files_scanned: int
    bytes_scanned: int
    marker_counts: dict[str, int]
    uuid_pattern_count: int
    truncated: bool

    @property
    def has_project_markers(self) -> bool:
        return any(
            self.marker_counts.get(key, 0) > 0
            for key in ("project", "projects_path", "project_id", "api_organizations")
        )


def _profile_roots(home: Path | None = None) -> tuple[Path, ...]:
    home = (home or Path.home()).expanduser()
    roots: list[Path] = [
        home / ".config" / "Claude",
        home / "Library" / "Application Support" / "Claude",
    ]
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "Claude")
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return tuple(unique)


def _desktop_roots(home: Path | None = None) -> tuple[Path, ...]:
    override = os.environ.get("EVERSTATE_CLAUDE_DESKTOP_ROOT")
    roots: list[Path] = []
    if override:
        roots.append(Path(override).expanduser())
    roots.extend(root / "local-agent-mode-sessions" for root in _profile_roots(home))
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


def diagnose_claude_desktop_profiles(home: Path | None = None) -> list[ClaudeDesktopProfileDiagnosis]:
    """Inspect profile structure only. Never opens cookies, IndexedDB, Local Storage, or transcripts."""
    diagnoses: list[ClaudeDesktopProfileDiagnosis] = []
    for root in _profile_roots(home):
        indexeddb = root / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb"
        local_storage = root / "Local Storage" / "leveldb"
        local_agent = root / "local-agent-mode-sessions"
        spaces_count = 0
        if local_agent.is_dir():
            try:
                for account in local_agent.iterdir():
                    if not account.is_dir():
                        continue
                    for org in account.iterdir():
                        if org.is_dir() and (org / "spaces.json").is_file():
                            spaces_count += 1
            except OSError:
                pass
        diagnoses.append(
            ClaudeDesktopProfileDiagnosis(
                profile_root=root,
                exists=root.is_dir(),
                local_agent_root_exists=local_agent.is_dir(),
                spaces_file_count=spaces_count,
                claude_ai_indexeddb_exists=indexeddb.is_dir(),
                claude_ai_local_storage_exists=local_storage.is_dir(),
                cookies_store_exists=(root / "Cookies").is_file(),
            )
        )
    return diagnoses


_UUID_PATTERN = re.compile(
    rb"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)
_CLOUD_MARKERS: tuple[tuple[str, bytes], ...] = (
    ("project", b"project"),
    ("projects_path", b"/projects/"),
    ("project_id", b"project_id"),
    ("project_uuid", b"project_uuid"),
    ("api_organizations", b"api/organizations"),
    ("organization", b"organization"),
)


def probe_claude_cloud_cache(
    home: Path | None = None,
    *,
    max_total_bytes: int = 32 * 1024 * 1024,
    max_file_bytes: int = 8 * 1024 * 1024,
) -> list[ClaudeCloudCacheProbe]:
    """Count structural markers in Claude's claude.ai IndexedDB without emitting stored values.

    This intentionally does not parse or print project names, messages, cookies, tokens,
    instructions, or arbitrary cached records. It is a bounded binary marker probe used
    only to decide whether a local metadata extractor is plausible.
    """
    probes: list[ClaudeCloudCacheProbe] = []
    for profile_root in _profile_roots(home):
        indexeddb_root = profile_root / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb"
        if not indexeddb_root.is_dir():
            probes.append(
                ClaudeCloudCacheProbe(
                    profile_root=profile_root,
                    indexeddb_root=indexeddb_root,
                    files_scanned=0,
                    bytes_scanned=0,
                    marker_counts={key: 0 for key, _ in _CLOUD_MARKERS},
                    uuid_pattern_count=0,
                    truncated=False,
                )
            )
            continue

        counts = {key: 0 for key, _ in _CLOUD_MARKERS}
        files_scanned = 0
        bytes_scanned = 0
        uuid_count = 0
        truncated = False
        try:
            files = sorted(path for path in indexeddb_root.iterdir() if path.is_file())
        except OSError:
            files = []

        for path in files:
            if bytes_scanned >= max_total_bytes:
                truncated = True
                break
            try:
                size = path.stat().st_size
            except OSError:
                continue
            remaining = max_total_bytes - bytes_scanned
            read_limit = min(size, max_file_bytes, remaining)
            if read_limit <= 0:
                truncated = True
                break
            try:
                with path.open("rb") as handle:
                    data = handle.read(read_limit)
            except OSError:
                continue
            files_scanned += 1
            bytes_scanned += len(data)
            if size > read_limit:
                truncated = True
            lowered = data.lower()
            for key, marker in _CLOUD_MARKERS:
                counts[key] += lowered.count(marker)
            uuid_count += len(_UUID_PATTERN.findall(data))

        probes.append(
            ClaudeCloudCacheProbe(
                profile_root=profile_root,
                indexeddb_root=indexeddb_root,
                files_scanned=files_scanned,
                bytes_scanned=bytes_scanned,
                marker_counts=counts,
                uuid_pattern_count=uuid_count,
                truncated=truncated,
            )
        )
    return probes


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
        "folders", "folderAssignments", "folder_assignments", "folderPaths", "folder_paths",
        "directories", "roots", "localFolders", "local_folders",
    ):
        if key in space:
            values.extend(_extract_path_value(space[key]))
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
        projects.append(ClaudeDesktopProject(project_id, name, _extract_folders(space), path, account_id, org_id))
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


def associate_claude_desktop_project(desktop_project: ClaudeDesktopProject, registered_projects: Iterable[RegisteredProject]) -> ClaudeDesktopAssociation:
    registered = list(registered_projects)
    if not desktop_project.folders:
        return ClaudeDesktopAssociation(desktop_project, "UNKNOWN", None, (), "Claude Desktop project metadata exposed no local folder assignment; Everstate will not guess.")
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
        return ClaudeDesktopAssociation(desktop_project, "VERIFIED", candidates[0], candidates, "Unique local-folder match: " + "; ".join(evidence))
    if len(candidates) > 1:
        return ClaudeDesktopAssociation(desktop_project, "AMBIGUOUS", None, candidates, "Local folders match multiple canonical projects; Everstate will not guess.")
    return ClaudeDesktopAssociation(desktop_project, "UNKNOWN", None, (), "No registered Everstate project matches the Claude Desktop project's local folders.")
