from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import everstate.claude_desktop_cli as desktop_cli
from everstate.claude_desktop import probe_claude_cloud_cache
from everstate.claude_desktop_cli import app

runner = CliRunner()


def _indexeddb(home: Path) -> Path:
    root = home / ".config" / "Claude" / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb"
    root.mkdir(parents=True)
    return root


def test_cloud_probe_counts_markers_without_returning_values(tmp_path: Path) -> None:
    root = _indexeddb(tmp_path)
    secret_name = "Private Project Name"
    payload = (
        b'{"project_id":"123e4567-e89b-12d3-a456-426614174000",'
        b'"name":"' + secret_name.encode() + b'",'
        b'"url":"/projects/123e4567-e89b-12d3-a456-426614174000",'
        b'"endpoint":"api/organizations/org/projects"}'
    )
    (root / "000003.log").write_bytes(payload)

    probes = probe_claude_cloud_cache(tmp_path)
    item = next(probe for probe in probes if probe.profile_root == tmp_path / ".config" / "Claude")

    assert item.files_scanned == 1
    assert item.marker_counts["project"] > 0
    assert item.marker_counts["projects_path"] == 1
    assert item.marker_counts["project_id"] == 1
    assert item.marker_counts["api_organizations"] == 1
    assert item.uuid_pattern_count >= 1
    assert secret_name not in repr(item)


def test_cloud_probe_is_bounded(tmp_path: Path) -> None:
    root = _indexeddb(tmp_path)
    (root / "large.ldb").write_bytes(b"project" * 1000)

    probes = probe_claude_cloud_cache(tmp_path, max_total_bytes=64, max_file_bytes=64)
    item = next(probe for probe in probes if probe.profile_root == tmp_path / ".config" / "Claude")

    assert item.bytes_scanned == 64
    assert item.truncated is True


def test_cloud_probe_cli_prints_counts_only(monkeypatch, tmp_path: Path) -> None:
    root = _indexeddb(tmp_path)
    (root / "000003.log").write_bytes(b'project_id /projects/ api/organizations 123e4567-e89b-12d3-a456-426614174000')

    monkeypatch.setattr(desktop_cli, "probe_claude_cloud_cache", lambda: probe_claude_cloud_cache(tmp_path))
    result = runner.invoke(app, ["cloud-probe"])

    assert result.exit_code == 0
    assert "Claude Desktop cloud cache probe" in result.stdout
    assert "Project-related markers exist" in result.stdout
    assert "counts only" in result.stdout
    assert "123e4567-e89b-12d3-a456-426614174000" not in result.stdout
