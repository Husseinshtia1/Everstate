from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .service import EverstateService, stable_project_id
from .source_discovery import DiscoveredSession, discover_sessions
from .storage import LocalStore
from .transfer_plan import RegisteredProject, SourceEnvironment, list_registered_projects


class ProjectCandidateKind(StrEnum):
    GIT_PROJECT = "GIT_PROJECT"
    WORKSPACE_PROJECT = "WORKSPACE_PROJECT"


class ProjectCandidateRole(StrEnum):
    PRIMARY_PROJECT = "PRIMARY_PROJECT"
    EXPERIMENT_FAMILY = "EXPERIMENT_FAMILY"
    RUN_ARTIFACT = "RUN_ARTIFACT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ProjectCandidate:
    root_path: Path
    suggested_name: str
    session_count: int
    sources: tuple[SourceEnvironment, ...]
    already_registered: bool
    project_id: str
    kind: ProjectCandidateKind
    role: ProjectCandidateRole


@dataclass(frozen=True)
class WorkspaceFamily:
    root_path: Path
    suggested_name: str
    members: tuple[ProjectCandidate, ...]
    session_count: int
    sources: tuple[SourceEnvironment, ...]
    already_registered: bool
    project_id: str
    role: ProjectCandidateRole


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


def _candidate_root(session: DiscoveredSession) -> tuple[Path, ProjectCandidateKind] | None:
    cwd = session.working_directory
    if cwd is None:
        return None
    try:
        cwd = cwd.expanduser().resolve()
    except OSError:
        return None
    if not cwd.exists() or not cwd.is_dir():
        return None

    git_root = _git_toplevel(cwd)
    if git_root is not None:
        return git_root, ProjectCandidateKind.GIT_PROJECT

    return cwd, ProjectCandidateKind.WORKSPACE_PROJECT


def _looks_like_run_artifact(name: str) -> bool:
    normalized = name.lower()
    patterns = (
        r"^agent[_-]",
        r"^run[_-]",
        r"^rollout[_-]",
        r"^attempt[_-]",
        r"^trial[_-]",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _looks_like_experiment_family(name: str) -> bool:
    normalized = name.lower()
    tokens = ("acceptance", "benchmark", "evaluation", "eval", "experiment", "test-harness", "test_harness")
    return any(token in normalized for token in tokens)


def classify_candidate_role(root: Path, kind: ProjectCandidateKind) -> ProjectCandidateRole:
    if kind is ProjectCandidateKind.GIT_PROJECT:
        return ProjectCandidateRole.PRIMARY_PROJECT
    if _looks_like_run_artifact(root.name):
        return ProjectCandidateRole.RUN_ARTIFACT
    return ProjectCandidateRole.UNKNOWN


def classify_family_role(root: Path, members: tuple[ProjectCandidate, ...]) -> ProjectCandidateRole:
    if _looks_like_experiment_family(root.name):
        return ProjectCandidateRole.EXPERIMENT_FAMILY
    if members and all(member.role is ProjectCandidateRole.RUN_ARTIFACT for member in members):
        return ProjectCandidateRole.EXPERIMENT_FAMILY
    return ProjectCandidateRole.UNKNOWN


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
            resolved = _candidate_root(session)
            if resolved is None:
                continue
            root, kind = resolved
            entry = grouped.setdefault(root, {"count": 0, "sources": set(), "kind": kind})
            entry["count"] = int(entry["count"]) + 1
            cast_sources = entry["sources"]
            assert isinstance(cast_sources, set)
            cast_sources.add(source)
            if kind is ProjectCandidateKind.GIT_PROJECT:
                entry["kind"] = kind

    candidates: list[ProjectCandidate] = []
    for root, entry in grouped.items():
        source_set = entry["sources"]
        assert isinstance(source_set, set)
        kind = entry["kind"]
        assert isinstance(kind, ProjectCandidateKind)
        candidates.append(
            ProjectCandidate(
                root_path=root,
                suggested_name=root.name,
                session_count=int(entry["count"]),
                sources=tuple(sorted(source_set, key=lambda item: item.value)),
                already_registered=root in registered,
                project_id=(registered[root].project_id if root in registered else stable_project_id(root)),
                kind=kind,
                role=classify_candidate_role(root, kind),
            )
        )
    return sorted(candidates, key=lambda item: (-item.session_count, str(item.root_path)))


def _unsafe_family_root(path: Path) -> bool:
    resolved = path.resolve()
    home = Path.home().resolve()
    unsafe = {
        Path("/").resolve(),
        home,
        (home / "Downloads").resolve(),
        (home / "Desktop").resolve(),
        (home / "Documents").resolve(),
        Path("/tmp").resolve(),
        Path("/var/tmp").resolve(),
    }
    return resolved in unsafe


def _deepest_safe_common_parent(paths: list[Path]) -> Path | None:
    if len(paths) < 2:
        return None
    try:
        common = Path(os.path.commonpath([str(path.resolve()) for path in paths])).resolve()
    except (OSError, ValueError):
        return None
    if _unsafe_family_root(common):
        return None
    if common in {path.resolve() for path in paths}:
        return None
    return common


def discover_workspace_families(
    store: LocalStore,
    candidates: list[ProjectCandidate] | None = None,
) -> list[WorkspaceFamily]:
    items = candidates if candidates is not None else discover_project_candidates(store)
    workspace_items = [item for item in items if item.kind is ProjectCandidateKind.WORKSPACE_PROJECT]
    if len(workspace_items) < 2:
        return []

    by_parent: dict[Path, list[ProjectCandidate]] = {}
    for item in workspace_items:
        by_parent.setdefault(item.root_path.parent.resolve(), []).append(item)

    candidate_groups: list[tuple[Path, list[ProjectCandidate]]] = []
    consumed: set[Path] = set()
    for parent, members in by_parent.items():
        if len(members) >= 2 and not _unsafe_family_root(parent):
            candidate_groups.append((parent, members))
            consumed.update(member.root_path for member in members)

    remaining = [item for item in workspace_items if item.root_path not in consumed]
    common = _deepest_safe_common_parent([item.root_path for item in remaining])
    if common is not None:
        members = [item for item in remaining if common in item.root_path.parents]
        if len(members) >= 2:
            candidate_groups.append((common, members))

    registered = {project.root_path.resolve(): project for project in list_registered_projects(store)}
    families: list[WorkspaceFamily] = []
    seen_roots: set[Path] = set()
    for root, members in candidate_groups:
        root = root.resolve()
        if root in seen_roots or len(members) < 2:
            continue
        seen_roots.add(root)
        source_set = {source for member in members for source in member.sources}
        member_tuple = tuple(sorted(members, key=lambda item: str(item.root_path)))
        families.append(
            WorkspaceFamily(
                root_path=root,
                suggested_name=root.name,
                members=member_tuple,
                session_count=sum(member.session_count for member in members),
                sources=tuple(sorted(source_set, key=lambda item: item.value)),
                already_registered=root in registered,
                project_id=(registered[root].project_id if root in registered else stable_project_id(root)),
                role=classify_family_role(root, member_tuple),
            )
        )
    return sorted(families, key=lambda item: (-item.session_count, str(item.root_path)))


def register_project_candidate(store: LocalStore, candidate: ProjectCandidate) -> RegisteredProject:
    service = EverstateService(store)
    project_id = service.init_project(candidate.root_path)
    return RegisteredProject(project_id=project_id, name=candidate.root_path.name, root_path=candidate.root_path)


def register_workspace_family(store: LocalStore, family: WorkspaceFamily) -> RegisteredProject:
    service = EverstateService(store)
    project_id = service.init_project(family.root_path)
    return RegisteredProject(project_id=project_id, name=family.root_path.name, root_path=family.root_path)


def register_explicit_project_path(store: LocalStore, root_path: Path, name: str | None = None) -> RegisteredProject:
    root = root_path.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Project root does not exist or is not a directory: {root}")
    service = EverstateService(store)
    project_id = service.init_project(root)
    final_name = (name or root.name).strip()
    if not final_name:
        raise ValueError("Project name cannot be empty")
    store.upsert_project(project_id, final_name, root)
    return RegisteredProject(project_id=project_id, name=final_name, root_path=root)
