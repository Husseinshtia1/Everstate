from __future__ import annotations

from pathlib import Path

from everstate.continuity import ContinuationPacket
from everstate.handoff import prepare_handoff
from everstate.providers import get_provider


def test_supported_provider_commands_are_interactive() -> None:
    claude = get_provider("claude")
    codex = get_provider("codex")

    assert claude.interactive_command("continue") == ["claude", "continue"]
    assert codex.interactive_command("continue") == ["codex", "continue"]


def test_unknown_provider_is_rejected() -> None:
    try:
        get_provider("unknown")
    except ValueError as exc:
        assert "Supported providers" in str(exc)
    else:
        raise AssertionError("Unknown provider should be rejected")


def test_prepare_handoff_writes_local_version_pinned_packet(tmp_path: Path) -> None:
    packet = ContinuationPacket(
        project_id="proj_test",
        state_version=12,
        objective="Complete OAuth migration",
        current_task="Fix callback regression",
        decisions=["Provider B remains active"],
        constraints=["Do not change database schema"],
        failed_attempts=["Provider A fallback duplicated callbacks"],
        blockers=["Redirect URI test failing"],
        modified_files=["src/auth.py"],
        next_action="Run callback test in isolation",
    )

    result = prepare_handoff(tmp_path, packet, get_provider("codex"))

    assert result.launched is False
    assert result.path == tmp_path / ".everstate" / "handoffs" / "state-v12-codex.md"
    assert result.path.exists()
    text = result.path.read_text(encoding="utf-8")
    assert "EVERSTATE CONTINUATION PACKET" in text
    assert "Provider B remains active" in text
    assert "Do not change database schema" in text
    assert result.command[0] == "codex"
    assert "Inspect the current working tree" in result.command[1]
