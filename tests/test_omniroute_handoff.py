from __future__ import annotations

from pathlib import Path

from everstate.continuity import ContinuationPacket
from everstate.handoff import prepare_handoff
from everstate.providers import ProviderAdapter, get_provider


def test_prepare_handoff_routes_verified_packet_through_omniroute_codex(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EVERSTATE_OMNIROUTE_MODEL", "cx/gpt-5.5")
    monkeypatch.setattr(
        ProviderAdapter,
        "resolve_executable",
        lambda self: "/tmp/omniroute" if self.executable == "omniroute" else "/tmp/codex",
    )
    packet = ContinuationPacket(
        project_id="proj_real",
        state_version=7,
        objective="KEEP_PROJECT_TRUTH",
        current_task="CONTINUE_AFTER_LIMIT",
        constraints=["ZERO_CROSS_PROJECT_LEAKAGE"],
        next_action="VERIFY_REPOSITORY_BEFORE_EDITING",
    )

    result = prepare_handoff(tmp_path, packet, get_provider("codex-omniroute"))

    assert result.path.name == "state-v7-codex-omniroute.md"
    assert result.command[:6] == [
        "/tmp/omniroute",
        "run",
        "codex",
        "--model",
        "cx/gpt-5.5",
        "--",
    ]
    prompt = result.command[-1]
    assert "PROJECT ID: proj_real" in prompt
    assert "STATE VERSION: 7" in prompt
    assert "ZERO_CROSS_PROJECT_LEAKAGE" in prompt
    assert "VERIFY_REPOSITORY_BEFORE_EDITING" in prompt
    assert result.launched is False
