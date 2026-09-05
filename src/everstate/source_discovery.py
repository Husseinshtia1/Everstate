from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from .transfer_plan import RegisteredProject, SourceEnvironment


class AssociationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DiscoveredSession:
    source: SourceEnvironment
    session_id: str
    storage_path: Path
    working_directory: Path | None
    updated_at: datetime
    metadata_only: bool = True


@dataclass(frozen=True)
class SessionAssociation:
    session: DiscoveredSession
    status: AssociationStatus
    project: RegisteredProject | None
    candidates: tuple[RegisteredProject, ...]
    detail: str


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _extract_path_from_jsonl(path: Path, *, max_lines: int = 40, max_bytes: int = 131072) -> Path | None:
    """Read a bounded metadata prefix only; never ingest the transcript body."""
    consumed = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                if index >= max_lines:
                    break
                consumed += len(line.encode("utf-8", errors="ignore"))
                if consumed > max_bytes:
                    break
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                candidates = [record.get("cwd"), record.get("projectPath"), record.get("project_path")]
                payload = record.get("payload")
                if isinstance(payload, dict):
                    candidates.extend([payload.get("cwd"), payload.get("projectPath"), payload.get("project_path")])
                for value in candidates:
                    if isinstance(value, str) and value.strip():
                        return Path(value).expanduser()
    except OSError:
        return None
    return None


def discover_codex_sessions(home: Path | None = None) -> list[DiscoveredSession]:
    root = (home or Path.home()) / ".codex" / "sessions"
    if not root.exists():
        return []
    sessions: list[DiscoveredSession] = []
    for path in root.rglob("*.jsonl"):
        if path.is_file():
            sessions.append(
                DiscoveredSession(
                    source=SourceEnvironment.CODEX,
                    session_id=path.stem,
                    storage_path=path,
                    working_directory=_extract_path_from_jsonl(path),
                    updated_at=_mtime(path),
                )
            )
    return sorted(sessions, key=lambda item: item.updated_at, reverse=True)


def discover_claude_code_sessions(home: Path | None = None) -> list[DiscoveredSession]:
    root = (home or Path.home()) / ".claude" / "projects"
    if not root.exists():
        return []
    sessions: list[DiscoveredSession] = []
    for project_dir in root.iterdir():
        if not project_dir.is_dir():
            continue
        for path in project_dir.glob("*.jsonl"):
            if path.is_file():
                sessions.append(
                    DiscoveredSession(
                        source=SourceEnvironment.CLAUDE_CODE,
                        session_id=path.stem,
                        storage_path=path,
                        working_directory=_extract_path_from_jsonl(path),
                        updated_at=_mtime(path),
                    )
                )
    return sorted(sessions, key=lambda item: item.updated_at, reverse=True)


def discover_sessions(source: SourceEnvironment, home: Path | None = None) -> list[DiscoveredSession]:
    if source is SourceEnvironment.CODEX:
        return discover_codex_sessions(home)
    if source is SourceEnvironment.CLAUDE_CODE:
        return discover_claude_code_sessions(home)
    if source is SourceEnvironment.CLAUDE_DESKTOP:
        raise ValueError(
            "Claude Desktop project/session discovery is not treated as Claude Code discovery; "
            "no stable local project contract is enabled yet."
        )
    raise ValueError(f"Source discovery is not implemented for {source.value}")


def _contains(root: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def associate_session(session: DiscoveredSession, projects: Iterable[RegisteredProject]) -> SessionAssociation:
    registered = list(projects)
    cwd = session.working_directory
    if cwd is None:
        return SessionAssociation(
            session=session,
            status=AssociationStatus.UNKNOWN,
            project=None,
            candidates=(),
            detail="Session metadata did not expose a working directory; user selection is required.",
        )

    exact = [project for project in registered if project.root_path.resolve() == cwd.resolve()]
    if len(exact) == 1:
        return SessionAssociation(session, AssociationStatus.VERIFIED, exact[0], tuple(exact), "Exact project-root match.")
    if len(exact) > 1:
        return SessionAssociation(session, AssociationStatus.AMBIGUOUS, None, tuple(exact), "Multiple exact project-root matches.")

    containing = [project for project in registered if _contains(project.root_path, cwd)]
    if len(containing) == 1:
        return SessionAssociation(
            session,
            AssociationStatus.VERIFIED,
            containing[0],
            tuple(containing),
            "Working directory is uniquely inside the registered project root.",
        )
    if len(containing) > 1:
        ordered = tuple(sorted(containing, key=lambda project: str(project.root_path)))
        return SessionAssociation(
            session,
            AssociationStatus.AMBIGUOUS,
            None,
            ordered,
            "Working directory matches multiple registered projects; Everstate will not guess.",
        )

    return SessionAssociation(
        session=session,
        status=AssociationStatus.UNKNOWN,
        project=None,
        candidates=(),
        detail=f"No registered Everstate project matches working directory {cwd}.",
    )
