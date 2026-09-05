from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import everstate.claude_cloud_cli as cloud_cli
from everstate.claude_cloud_cli import app
from everstate.claude_cloud_projects import discover_claude_cloud_project_candidates

runner = CliRunner()


def _cache_file(home: Path, payload: bytes) -> Path:
    root = home / ".config" / "Claude" / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb"
    root.mkdir(parents=True)
    path = root / "000003.log"
    path.write_bytes(payload)
    return path


def test_strict_candidate_requires_uuid_project_marker_and_name(tmp_path: Path) -> None:
    project_id = "123e4567-e89b-42d3-a456-426614174000"
    _cache_file(
        tmp_path,
        f'prefix project cache {{"name":"Actual Cloud Project"}} xx {project_id} suffix'.encode(),
    )

    items = discover_claude_cloud_project_candidates(tmp_path)

    assert len(items) == 1
    assert items[0].project_id == project_id
    assert items[0].name == "Actual Cloud Project"
    assert items[0].confidence == "STRICT"
    assert items[0].selectable is True


def test_uuid_near_project_without_name_is_unverified(tmp_path: Path) -> None:
    project_id = "123e4567-e89b-42d3-a456-426614174001"
    _cache_file(tmp_path, f"project metadata {project_id}".encode())

    items = discover_claude_cloud_project_candidates(tmp_path)

    assert len(items) == 1
    assert items[0].name is None
    assert items[0].confidence == "UNVERIFIED"
    assert items[0].selectable is False


def test_uuid_without_project_context_is_ignored(tmp_path: Path) -> None:
    _cache_file(tmp_path, b"random 123e4567-e89b-42d3-a456-426614174002 unrelated")

    assert discover_claude_cloud_project_candidates(tmp_path) == []


def test_deduplicates_uuid_and_prefers_strict_candidate(tmp_path: Path) -> None:
    project_id = "123e4567-e89b-42d3-a456-426614174003"
    root = tmp_path / ".config" / "Claude" / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb"
    root.mkdir(parents=True)
    (root / "000001.log").write_bytes(f"project {project_id}".encode())
    (root / "000002.ldb").write_bytes(
        f'project {project_id} {{"title":"Preferred Name"}}'.encode()
    )

    items = discover_claude_cloud_project_candidates(tmp_path)

    assert len(items) == 1
    assert items[0].confidence == "STRICT"
    assert items[0].name == "Preferred Name"


def test_cli_strict_only_hides_unverified(monkeypatch, tmp_path: Path) -> None:
    strict_id = "123e4567-e89b-42d3-a456-426614174004"
    unverified_id = "123e4567-e89b-42d3-a456-426614174005"
    strict_file = tmp_path / "strict.log"
    unverified_file = tmp_path / "unverified.log"

    from everstate.claude_cloud_projects import ClaudeCloudProjectCandidate

    monkeypatch.setattr(
        cloud_cli,
        "discover_claude_cloud_project_candidates",
        lambda: [
            ClaudeCloudProjectCandidate(strict_id, "Real Project", "STRICT", strict_file, ("uuid_near_project_marker", "name_or_title_in_same_window")),
            ClaudeCloudProjectCandidate(unverified_id, None, "UNVERIFIED", unverified_file, ("uuid_near_project_marker",)),
        ],
    )

    result = runner.invoke(app, ["--strict-only"])

    assert result.exit_code == 0
    assert "Real Project" in result.stdout
    assert strict_id in result.stdout
    assert unverified_id not in result.stdout
    assert "STRICT: 1" in result.stdout
    assert "UNVERIFIED: 0" in result.stdout
