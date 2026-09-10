from __future__ import annotations

from pathlib import Path

import pytest

from everstate.acceptance import ContinuityScenario
from everstate.live_acceptance import StateLevel, run_real_acceptance, seed_state
from everstate.providers import get_provider
from everstate.service import EverstateService
from everstate.storage import LocalStore


class NeverProvider:
    name = "Never Provider"

    def launch(self, root: Path, prompt: str) -> int:  # pragma: no cover
        raise AssertionError("provider must not launch")


def _service(tmp_path: Path) -> EverstateService:
    return EverstateService(LocalStore(tmp_path / "state.db"))


def _scenario(**overrides) -> ContinuityScenario:
    payload = {
        "name": "hardening",
        "objective": "Build safely",
        "current_task": "Implement feature",
        "decisions": ["Use stdlib"],
        "constraints": ["Do not touch policy"],
        "failed_attempts": ["Previous shortcut failed"],
        "blockers": ["Implementation missing"],
        "next_action": "Implement and verify",
        "required_changed_files": [],
        "protected_files": [],
        "forbidden_substrings": {},
        "validation_commands": [],
    }
    payload.update(overrides)
    return ContinuityScenario.model_validate(payload)


def test_codex_real_acceptance_uses_headless_exec_contract() -> None:
    provider = get_provider("codex")
    command = provider.automation_command("Build it")
    assert command[1:] == [
        "-c",
        'approval_policy="never"',
        "-c",
        "sandbox_workspace_write.network_access=false",
        "exec",
        "--sandbox",
        "workspace-write",
        "--ephemeral",
        "Build it",
    ]
    assert "--full-auto" not in command
    assert "--ask-for-approval" not in command
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert provider.automation_supported


def test_unverified_provider_headless_contract_fails_closed() -> None:
    provider = get_provider("claude")
    assert not provider.automation_supported
    with pytest.raises(RuntimeError, match="non-interactive automation contract"):
        provider.automation_command("Build it")


def test_critical_state_cannot_disable_council(tmp_path: Path) -> None:
    template = tmp_path / "template"
    template.mkdir()
    with pytest.raises(ValueError, match="critical state level requires independent council review"):
        run_real_acceptance(
            service=_service(tmp_path),
            template=template,
            workspace=tmp_path / "workspace",
            scenario=_scenario(),
            provider=NeverProvider(),
            state_level=StateLevel.CRITICAL,
            require_council=False,
        )


def test_full_state_rejects_incomplete_scenario(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    scenario = _scenario(failed_attempts=[], blockers=[])
    with pytest.raises(ValueError, match="missing: failed_attempts, blockers"):
        seed_state(_service(tmp_path), root, scenario, StateLevel.FULL)
