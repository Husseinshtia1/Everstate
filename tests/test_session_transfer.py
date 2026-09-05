from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import everstate.session_transfer as session_transfer
from everstate.source_discovery import DiscoveredSession
from everstate.storage import LocalStore
from everstate.transfer_plan import SourceEnvironment


def _store(tmp_path: Path) -> LocalStore:
    return LocalStore(tmp_path / "everstate.db")


def _register(store: LocalStore, project_id: str, name: str, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    store.upsert_project(project_id, name, root)


def _session(source: SourceEnvironment, session_id: str, cwd: Path, tmp_path: Path) -> DiscoveredSession:
    return DiscoveredSession(source, session_id, tmp_path / f"{session_id}.jsonl", cwd, datetime.now(timezone.utc))


def test_verified_session_selects_project_without_user_override(monkeypatch, tmp_path: Path) -> None:
    store = _store(tmp_path)
    root = tmp_path / "alpha"
    _register(store, "proj_alpha", "Alpha", root)
    found = _session(SourceEnvironment.CODEX, "s1", root, tmp_path)
    monkeypatch.setattr(session_transfer, "discover_sessions", lambda source, home=None: [found])

    review = session_transfer.build_session_transfer_review(
        store, source=SourceEnvironment.CODEX, destination="gemini", session_id="s1"
    )

    assert review.plan.projects[0].project_id == "proj_alpha"
    assert review.project_selection == "verified-session-metadata"


def test_unknown_session_requires_explicit_project(monkeypatch, tmp_path: Path) -> None:
    store = _store(tmp_path)
    root = tmp_path / "alpha"
    other = tmp_path / "unknown"
    other.mkdir()
    _register(store, "proj_alpha", "Alpha", root)
    found = _session(SourceEnvironment.CODEX, "s2", other, tmp_path)
    monkeypatch.setattr(session_transfer, "discover_sessions", lambda source, home=None: [found])

    with pytest.raises(ValueError, match="specify --project explicitly"):
        session_transfer.build_session_transfer_review(
            store, source=SourceEnvironment.CODEX, destination="gemini", session_id="s2"
        )


def test_ambiguous_session_requires_explicit_candidate_project(monkeypatch, tmp_path: Path) -> None:
    store = _store(tmp_path)
    outer = tmp_path / "repo"
    inner = outer / "nested"
    cwd = inner / "src"
    cwd.mkdir(parents=True)
    _register(store, "outer", "Outer", outer)
    _register(store, "inner", "Inner", inner)
    found = _session(SourceEnvironment.CLAUDE_CODE, "s3", cwd, tmp_path)
    monkeypatch.setattr(session_transfer, "discover_sessions", lambda source, home=None: [found])

    with pytest.raises(ValueError, match="specify --project explicitly"):
        session_transfer.build_session_transfer_review(
            store, source=SourceEnvironment.CLAUDE_CODE, destination="codex", session_id="s3"
        )

    review = session_transfer.build_session_transfer_review(
        store,
        source=SourceEnvironment.CLAUDE_CODE,
        destination="codex",
        session_id="s3",
        project_selector="inner",
    )
    assert review.plan.projects[0].project_id == "inner"
    assert review.project_selection == "explicit-user"


def test_verified_session_rejects_conflicting_explicit_project(monkeypatch, tmp_path: Path) -> None:
    store = _store(tmp_path)
    alpha = tmp_path / "alpha"
    beta = tmp_path / "beta"
    _register(store, "alpha", "Alpha", alpha)
    _register(store, "beta", "Beta", beta)
    found = _session(SourceEnvironment.CODEX, "s4", alpha, tmp_path)
    monkeypatch.setattr(session_transfer, "discover_sessions", lambda source, home=None: [found])

    with pytest.raises(ValueError, match="conflicts with verified session metadata"):
        session_transfer.build_session_transfer_review(
            store,
            source=SourceEnvironment.CODEX,
            destination="gemini",
            session_id="s4",
            project_selector="beta",
        )


def test_unknown_session_id_is_rejected(monkeypatch, tmp_path: Path) -> None:
    store = _store(tmp_path)
    monkeypatch.setattr(session_transfer, "discover_sessions", lambda source, home=None: [])

    with pytest.raises(ValueError, match="Unknown codex session"):
        session_transfer.build_session_transfer_review(
            store, source=SourceEnvironment.CODEX, destination="gemini", session_id="missing"
        )


def test_desktop_session_discovery_is_not_claimed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="not enabled for claude-desktop"):
        session_transfer.build_session_transfer_review(
            store,
            source=SourceEnvironment.CLAUDE_DESKTOP,
            destination="gemini",
            session_id="desktop-1",
        )
