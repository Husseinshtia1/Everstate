from __future__ import annotations

from everstate.providers import get_provider


def test_codex_automation_uses_current_noninteractive_workspace_write_contract() -> None:
    provider = get_provider("codex")
    command = provider.automation_command("build the project")

    assert command[0].endswith("codex")
    assert command[1:] == [
        "exec",
        "--sandbox",
        "workspace-write",
        "--ask-for-approval",
        "never",
        "build the project",
    ]
    assert "--full-auto" not in command


def test_interactive_only_providers_are_not_silently_treated_as_automatable() -> None:
    assert get_provider("claude").automation_supported is False
    assert get_provider("gemini").automation_supported is False
    assert get_provider("codex-ollama").automation_supported is False
    assert get_provider("codex-omniroute").automation_supported is False
