from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from everstate.source_discovery import (
    AssociationStatus,
    DiscoveredSession,
    associate_session,
    discover_claude_code_sessions,
    discover_codex_sessions,
    discover_sessions,
)
from everstate.transfer_plan import RegisteredProject, SourceEnvironment


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_discovers_codex_session_from_bounded_metadata_prefix(tmp_path: Path) -> None:
    project = tmp_path / "work" / "alpha"
    project.mkdir(parents=True)
    session = tmp_path / ".codex" / "sessions" / "2026" / "09" / "rollout-abc.jsonl"
    _write_jsonl(session, [{"type": "session_meta", "payload": {"cwd": str(project), "id": "abc"}}, {"message": "do not need this"}])

    found = discover_codex_sessions(tmp_path)

    assert len(found) == 1
    assert found[0].source is SourceEnvironment.CODEX
    assert found[0].working_directory == project
    assert found[0].metadata_only is True


def test_discovers_claude_code_session_metadata(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    session = tmp_path / ".claude" / "projects" / "-tmp-repo" / "session-1.jsonl"
    _write_jsonl(session, [{"cwd": str(project), "sessionId": "session-1"}])

    found = discover_claude_code_sessions(tmp_path)

    assert len(found) == 1
    assert found[0].source is SourceEnvironment.CLAUDE_CODE
    assert found[0].working_directory == project


def test_exact_project_association_is_verified(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    registered = RegisteredProject("proj_a", "A", root)
    session = DiscoveredSession(SourceEnvironment.CODEX, "s1", tmp_path / "s1.jsonl", root, datetime.now(timezone.utc))

    result = associate_session(session, [registered])

    assert result.status is AssociationStatus.VERIFIED
    assert result.project == registered


def test_unique_subdirectory_association_is_verified(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    cwd = root / "src" / "pkg"
    cwd.mkdir(parents=True)
    registered = RegisteredProject("proj_a", "A", root)
    session = DiscoveredSession(SourceEnvironment.CLAUDE_CODE, "s2", tmp_path / "s2.jsonl", cwd, datetime.now(timezone.utc))

    result = associate_session(session, [registered])

    assert result.status is AssociationStatus.VERIFIED
    assert result.project == registered


def test_multiple_containing_projects_are_ambiguous_not_guessed(tmp_path: Path) -> None:
    outer = tmp_path / "repo"
    inner = outer / "nested"
    cwd = inner / "src"
    cwd.mkdir(parents=True)
    projects = [
        RegisteredProject("outer", "Outer", outer),
        RegisteredProject("inner", "Inner", inner),
    ]
    session = DiscoveredSession(SourceEnvironment.CODEX, "s3", tmp_path / "s3.jsonl", cwd, datetime.now(timezone.utc))

    result = associate_session(session, projects)

    assert result.status is AssociationStatus.AMBIGUOUS
    assert result.project is None
    assert {project.project_id for project in result.candidates} == {"outer", "inner"}


def test_missing_working_directory_is_unknown(tmp_path: Path) -> None:
    session = DiscoveredSession(SourceEnvironment.CODEX, "s4", tmp_path / "s4.jsonl", None, datetime.now(timezone.utc))

    result = associate_session(session, [])

    assert result.status is AssociationStatus.UNKNOWN
    assert result.project is None


def test_claude_desktop_does_not_masquerade_as_claude_code(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not treated as Claude Code discovery"):
        discover_sessions(SourceEnvironment.CLAUDE_DESKTOP, tmp_path)
