from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .service import EverstateService, stable_project_id
from .source_discovery import DiscoveredSession, discover_sessions
from .storage import LocalStore
from .transfer_plan import RegisteredProject, SourceEnvironment, list_registered_projects


@dataclass(frozen=True)
class ProjectCandidate:
    root_path: Path
    suggested_name: str
    session_count: int
    sources: tuple[SourceEnvironment, ...]
    already_registered: bool
    project_id: str


def _git_toplevel(path: Path) -> Path | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            text=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return Path(value).resolve() if value else None


def _candidate_root(session: DiscoveredSession) -> Path | None:
    cwd = session.working_directory
    if cwd is None:
        return None
    try:
        cwd = cwd.expanduser().resolve()
    except OSError:
        return None
    if not cwd.exists() or not cwd.is_dir():
        return None
    return _git_toplevel(cwd)


def discover_project_candidates(
    store: LocalStore,
    *,
    sources: tuple[SourceEnvironment, ...] = (SourceEnvironment.CODEX, SourceEnvironment.CLAUDE_CODE),
    session_limit_per_source: int = 500,
) -> list[ProjectCandidate]:
    registered = {project.root_path.resolve(): project for project in list_registered_projects(store)}
    grouped: dict[Path, dict[str, object]] = {}

    for source in sources:
        sessions = discover_sessions(source)[:session_limit_per_source]
        for session in sessions:
            root = _candidate_root(session)
            if root is None:
                continue
            entry = grouped.setdefault(root, {"count": 0, "sources": set()})
            entry["count"] = int(entry["count"]) + 1
            cast_sources = entry["sources"]
            assert isinstance(cast_sources, set)
            cast_sources.add(source)

    candidates: list[ProjectCandidate] = []
    for root, entry in grouped.items():
        source_set = entry["sources"]
        assert isinstance(source_set, set)
        candidates.append(
            ProjectCandidate(
                root_path=root,
                suggested_name=root.name,
                session_count=int(entry["count"]),
                sources=tuple(sorted(source_set, key=lambda item: item.value)),
                already_registered=root in registered,
                project_id=(registered[root].project_id if root in registered else stable_project_id(root)),
            )
        )
    return sorted(candidates, key=lambda item: (-item.session_count, str(item.root_path)))


def register_project_candidate(store: LocalStore, candidate: ProjectCandidate) -> RegisteredProject:
    service = EverstateService(store)
    project_id = service.init_project(candidate.root_path)
    return RegisteredProject(project_id=project_id, name=candidate.root_path.name, root_path=candidate.root_path)
