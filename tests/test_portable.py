from __future__ import annotations

import json
from pathlib import Path

import everstate.portable as portable
from everstate.continuity import ContinuationPacket
from everstate.portable import PORTABLE_FORMAT, copy_packet, export_packet, portable_markdown


def packet() -> ContinuationPacket:
    return ContinuationPacket(
        project_id="proj_test",
        state_version=42,
        objective="Keep work moving",
        current_task="Continue on another provider",
        decisions=["Preserve current architecture"],
        constraints=["Do not weaken security"],
        failed_attempts=["Provider A is unavailable"],
        blockers=["Current provider exhausted"],
        modified_files=["src/auth.py"],
        unresolved_conflicts=[],
        next_action="Continue from verified state",
    )


def test_export_packet_writes_markdown_and_json_for_same_state_version(tmp_path: Path) -> None:
    result = export_packet(tmp_path, packet())

    assert result.markdown_path.exists()
    assert result.json_path.exists()
    assert result.markdown_path.name == "everstate-state-v42.md"
    assert result.json_path.name == "everstate-state-v42.json"

    markdown = result.markdown_path.read_text(encoding="utf-8")
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert "EVERSTATE CONTINUATION PACKET" in markdown
    assert "Do not weaken security" in markdown
    assert payload["format"] == PORTABLE_FORMAT
    assert payload["state_version"] == 42
    assert payload["continuation"]["state_version"] == 42
    assert payload["continuation"]["failed_attempts"] == ["Provider A is unavailable"]


def test_explicit_output_directory_is_supported(tmp_path: Path) -> None:
    destination = tmp_path / "portable"

    result = export_packet(tmp_path, packet(), destination)

    assert result.markdown_path.parent == destination.resolve()
    assert result.json_path.parent == destination.resolve()


def test_portable_markdown_warns_to_check_newer_repository_evidence() -> None:
    text = portable_markdown(packet())

    assert "inspect newer repository evidence" in text
    assert "State version: `42`" in text


def test_copy_returns_none_when_no_clipboard_tool_exists(monkeypatch) -> None:
    monkeypatch.setattr(portable.shutil, "which", lambda executable: None)

    assert copy_packet(packet()) is None


def test_copy_sends_only_packet_text_to_detected_clipboard(monkeypatch) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        portable.shutil,
        "which",
        lambda executable: "/usr/bin/wl-copy" if executable == "wl-copy" else None,
    )

    def fake_run(command, **kwargs):
        calls["command"] = command
        calls["input"] = kwargs["input"]
        return None

    monkeypatch.setattr(portable.subprocess, "run", fake_run)

    executable = copy_packet(packet())

    assert executable == "/usr/bin/wl-copy"
    assert calls["command"] == ["/usr/bin/wl-copy"]
    assert "EVERSTATE CONTINUATION PACKET" in str(calls["input"])
