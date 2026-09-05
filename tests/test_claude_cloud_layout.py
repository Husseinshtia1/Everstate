from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import everstate.claude_desktop_cli as desktop_cli
from everstate.claude_cloud_layout import ClaudeCloudLayoutDiagnosis, diagnose_claude_cloud_layout
from everstate.claude_desktop_cli import app

runner = CliRunner()


def _cache(home: Path, payload: bytes) -> Path:
    root = home / ".config" / "Claude" / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb"
    root.mkdir(parents=True)
    path = root / "000003.log"
    path.write_bytes(payload)
    return path


def test_layout_counts_proximity_without_exposing_values(tmp_path: Path) -> None:
    project_id = b"123e4567-e89b-42d3-a456-426614174000"
    payload = b"project " + b"x" * 100 + b" " + project_id + b" " + b"y" * 100 + b" title"
    _cache(tmp_path, payload)

    item = diagnose_claude_cloud_layout(tmp_path)[0]

    assert item.uuid_ascii == 1
    assert item.project_ascii == 1
    assert item.name_ascii == 1
    assert item.uuid_with_project_1536 == 1
    assert item.uuid_with_name_4096 == 1


def test_layout_detects_utf16le_markers(tmp_path: Path) -> None:
    uuid = "123e4567-e89b-42d3-a456-426614174000".encode("utf-16le")
    payload = "project".encode("utf-16le") + b"\x00\x00" + uuid + b"\x00\x00" + "title".encode("utf-16le")
    _cache(tmp_path, payload)

    item = diagnose_claude_cloud_layout(tmp_path)[0]

    assert item.uuid_utf16le == 1
    assert item.project_utf16le >= 1
    assert item.name_utf16le >= 1


def test_cloud_layout_cli_prints_counts_only(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        desktop_cli,
        "diagnose_claude_cloud_layout",
        lambda: [
            ClaudeCloudLayoutDiagnosis(
                profile_root=tmp_path,
                files_scanned=2,
                bytes_scanned=1000,
                uuid_ascii=23,
                uuid_utf16le=0,
                project_ascii=18,
                project_utf16le=0,
                name_ascii=9,
                name_utf16le=0,
                uuid_with_project_1536=0,
                uuid_with_project_4096=2,
                uuid_with_project_16384=5,
                uuid_with_project_65536=9,
                uuid_with_name_4096=3,
                truncated=True,
            )
        ],
    )

    result = runner.invoke(app, ["cloud-layout"])

    assert result.exit_code == 0
    assert "Claude Desktop cloud cache layout" in result.stdout
    assert "23" in result.stdout
    assert "A/U = ASCII/UTF-16LE marker counts" in result.stdout
    assert "123e4567" not in result.stdout
