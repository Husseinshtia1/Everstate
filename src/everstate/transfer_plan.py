from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .storage import LocalStore


class SourceEnvironment(StrEnum):
    CURRENT_WORKTREE = "current-worktree"
    CLAUDE_DESKTOP = "claude-desktop"
    CLAUDE_CODE = "claude-code"
    CODEX = "codex"
    GEMINI = "gemini"
    LOCAL = "local"
    MANUAL = "manual"
    OTHER = "other"


@dataclass(frozen=True)
class RegisteredProject:
    project_id: str
    name: str
    root_path: Path


@dataclass(frozen=True)
class TransferPlan:
    source: SourceEnvironment
    destination: str
    projects: tuple[RegisteredProject, ...]
    scope: str

    def summary(self) -> str:
        lines = [
            "EVERSTATE TRANSFER PLAN",
            f"SOURCE: {self.source.value}",
            f"DESTINATION: {self.destination}",
            f"SCOPE: {self.scope}",
            f"PROJECT COUNT: {len(self.projects)}",
            "PROJECTS:",
        ]
        lines.extend(
            f"- {project.name} [{project.project_id}] {project.root_path}"
            for project in self.projects
        )
        return "\n".join(lines)


def list_registered_projects(store: LocalStore) -> list[RegisteredProject]:
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT id, name, root_path FROM projects ORDER BY updated_at DESC, name ASC"
        ).fetchall()
    return [
        RegisteredProject(
            project_id=row["id"],
            name=row["name"],
            root_path=Path(row["root_path"]),
        )
        for row in rows
    ]


def _resolve_selector(selector: str, projects: list[RegisteredProject]) -> RegisteredProject:
    candidate = Path(selector).expanduser()
    candidate_resolved = candidate.resolve() if candidate.exists() else None

    matches = [
        project
        for project in projects
        if selector == project.project_id
        or selector == project.name
        or (candidate_resolved is not None and candidate_resolved == project.root_path.resolve())
    ]
    if not matches:
        raise ValueError(f"Unknown Everstate project selector: {selector}")
    if len(matches) > 1:
        ids = ", ".join(project.project_id for project in matches)
        raise ValueError(f"Ambiguous project selector {selector!r}; use a project id instead ({ids})")
    return matches[0]


def build_transfer_plan(
    store: LocalStore,
    *,
    source: SourceEnvironment,
    destination: str,
    project_selectors: list[str] | None = None,
    all_projects: bool = False,
    confirm_all: bool = False,
) -> TransferPlan:
    destination = destination.strip()
    if not destination:
        raise ValueError("Destination environment is required")

    selectors = [value.strip() for value in (project_selectors or []) if value.strip()]
    if all_projects and selectors:
        raise ValueError("Choose explicit projects or --all, not both")
    if not all_projects and not selectors:
        raise ValueError("Select at least one project; Everstate never assumes all projects")
    if all_projects and not confirm_all:
        raise ValueError("Transferring all projects requires explicit confirmation")

    registered = list_registered_projects(store)
    if not registered:
        raise ValueError("No projects are registered in Everstate")

    if all_projects:
        selected = registered
        scope = "all"
    else:
        selected = []
        seen: set[str] = set()
        for selector in selectors:
            project = _resolve_selector(selector, registered)
            if project.project_id not in seen:
                selected.append(project)
                seen.add(project.project_id)
        scope = "single" if len(selected) == 1 else "selected"

    return TransferPlan(
        source=source,
        destination=destination,
        projects=tuple(selected),
        scope=scope,
    )
