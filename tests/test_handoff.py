from __future__ import annotations

from pathlib import Path

from everstate.continuity import ContinuationPacket
from everstate.handoff import prepare_handoff
from everstate.providers import get_provider


def test_supported_provider_commands_are_interactive(monkeypatch) -> None:
    monkeypatch.setattr("everstate.providers.shutil.which", lambda _: None)
    monkeypatch.setattr("everstate.providers.ProviderAdapter.resolve_executable", lambda self: self.executable)

    claude = get_provider("claude")
    codex = get_provider("codex")
    gemini = get_provider("gemini")
    local = get_provider("codex-ollama")

    assert claude.interactive_command("continue") == ["claude", "continue"]
    assert codex.interactive_command("continue") == ["codex", "continue"]
    assert gemini.interactive_command("continue") == ["gemini", "-i", "continue"]
    assert local.interactive_command("continue") == [
        "codex",
        "--oss",
        "--local-provider",
        "ollama",
        "-m",
        "gpt-oss:20b",
        "continue",
    ]


def test_local_model_can_be_selected_without_changing_cloud_codex(monkeypatch) -> None:
    monkeypatch.setattr("everstate.providers.ProviderAdapter.resolve_executable", lambda self: self.executable)
    monkeypatch.setenv("EVERSTATE_OLLAMA_MODEL", "qwen3-coder:latest")

    local = get_provider("codex-ollama")
    cloud = get_provider("codex")

    assert local.interactive_command("continue")[-3:] == ["qwen3-coder:latest", "continue"][-2:] if False else local.interactive_command("continue")[-3:]
    assert local.interactive_command("continue") == [
        "codex",
        "--oss",
        "--local-provider",
        "ollama",
        "-m",
        "qwen3-coder:latest",
        "continue",
    ]
    assert cloud.interactive_command("continue") == ["codex", "continue"]


def test_codex_is_discovered_from_user_npm_prefix_when_not_on_path(tmp_path: Path, monkeypatch) -> None:
    fake_home = tmp_path / "home"
    binary = fake_home / ".npm-global" / "bin" / "codex"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)

    monkeypatch.setattr("everstate.providers.shutil.which", lambda _: None)
    monkeypatch.setattr("everstate.providers.Path.home", lambda: fake_home)

    codex = get_provider("codex")

    assert codex.available() is True
    assert codex.resolve_executable() == str(binary)
    assert codex.interactive_command("continue") == [str(binary), "continue"]


def test_gemini_is_discovered_from_user_npm_prefix_when_not_on_path(tmp_path: Path, monkeypatch) -> None:
    fake_home = tmp_path / "home"
    binary = fake_home / ".npm-global" / "bin" / "gemini"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)

    monkeypatch.setattr("everstate.providers.shutil.which", lambda _: None)
    monkeypatch.setattr("everstate.providers.Path.home", lambda: fake_home)

    gemini = get_provider("gemini")

    assert gemini.available() is True
    assert gemini.resolve_executable() == str(binary)
    assert gemini.interactive_command("continue") == [str(binary), "-i", "continue"]


def test_provider_binary_can_be_overridden(tmp_path: Path, monkeypatch) -> None:
    binary = tmp_path / "codex-custom"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)

    monkeypatch.setattr("everstate.providers.shutil.which", lambda _: None)
    monkeypatch.setenv("EVERSTATE_CODEX_BIN", str(binary))

    codex = get_provider("codex")
    assert codex.resolve_executable() == str(binary)


def test_unknown_provider_is_rejected() -> None:
    try:
        get_provider("unknown")
    except ValueError as exc:
        assert "Supported providers" in str(exc)
    else:
        raise AssertionError("Unknown provider should be rejected")


def _packet() -> ContinuationPacket:
    return ContinuationPacket(
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


def test_prepare_handoff_writes_local_version_pinned_packet(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("everstate.providers.ProviderAdapter.resolve_executable", lambda self: self.executable)
    result = prepare_handoff(tmp_path, _packet(), get_provider("codex"))

    assert result.launched is False
    assert result.path == tmp_path / ".everstate" / "handoffs" / "state-v12-codex.md"
    assert result.path.exists()
    text = result.path.read_text(encoding="utf-8")
    assert "EVERSTATE CONTINUATION PACKET" in text
    assert "Provider B remains active" in text
    assert "Do not change database schema" in text
    assert result.command[0] == "codex"
    assert "Inspect the current working tree" in result.command[-1]


def test_prepare_gemini_handoff_preserves_prompt_after_interactive_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("everstate.providers.ProviderAdapter.resolve_executable", lambda self: self.executable)
    result = prepare_handoff(tmp_path, _packet(), get_provider("gemini"))

    assert result.path == tmp_path / ".everstate" / "handoffs" / "state-v12-gemini.md"
    assert result.command[:2] == ["gemini", "-i"]
    assert "EVERSTATE CONTINUATION PACKET" in result.command[-1]
    assert "Inspect the current working tree" in result.command[-1]


def test_prepare_local_handoff_uses_oss_provider_and_installed_model(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("everstate.providers.ProviderAdapter.resolve_executable", lambda self: self.executable)
    monkeypatch.setenv("EVERSTATE_OLLAMA_MODEL", "qwen3-coder:latest")

    result = prepare_handoff(tmp_path, _packet(), get_provider("codex-ollama"))

    assert result.path == tmp_path / ".everstate" / "handoffs" / "state-v12-codex.md"
    assert result.command[:6] == [
        "codex",
        "--oss",
        "--local-provider",
        "ollama",
        "-m",
        "qwen3-coder:latest",
    ]
    assert "EVERSTATE CONTINUATION PACKET" in result.command[-1]
