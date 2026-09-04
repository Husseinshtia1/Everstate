from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import everstate.cli as cli_module
from everstate.cli import app
from everstate.continuity import ContinuationPacket
from everstate.handoff import HandoffResult
from everstate.provider_readiness import ProviderCapability, ProviderProbeResult, ProviderState


runner = CliRunner()


def probe(
    key: str,
    *,
    state: ProviderState = ProviderState.READY,
    coding: bool = True,
    repo: bool = True,
    local: bool = False,
    cloud: bool = True,
    manual: bool = False,
) -> ProviderProbeResult:
    return ProviderProbeResult(
        key=key,
        name=key,
        state=state,
        detail="test",
        executable=f"/tmp/{key}" if not manual else None,
        capability=ProviderCapability(
            coding_agent=coding,
            repository_access=repo,
            local=local,
            cloud=cloud,
            manual=manual,
        ),
    )


def packet(version: int = 12) -> ContinuationPacket:
    return ContinuationPacket(
        project_id="proj_test",
        state_version=version,
        objective="Continue safely",
        current_task="Fix the current bug",
        decisions=[],
        constraints=["Preserve security"],
        failed_attempts=[],
        blockers=[],
        modified_files=[],
        unresolved_conflicts=[],
        next_action="Continue",
    )


def test_continue_dry_run_shows_visible_recommendation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        cli_module,
        "probe_all_providers",
        lambda active=False: [
            probe("claude", state=ProviderState.LIMIT_REACHED),
            probe("codex"),
            probe("manual", state=ProviderState.ALWAYS_READY, coding=False, repo=False, cloud=False, manual=True),
        ],
    )

    result = runner.invoke(app, ["continue", "--path", str(tmp_path), "--dry-run"])

    assert result.exit_code == 0
    assert "Everstate continuation options" in result.stdout
    assert "Recommended continuation" in result.stdout
    assert "codex" in result.stdout
    assert "Dry run only" in result.stdout


def test_continue_ask_me_never_auto_selects(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        cli_module,
        "probe_all_providers",
        lambda active=False: [probe("codex")],
    )

    result = runner.invoke(app, ["continue", "--path", str(tmp_path), "--mode", "ask-me", "--dry-run"])

    assert result.exit_code == 0
    assert "No target was selected automatically" in result.stdout
    assert "--target <key>" in result.stdout


def test_continue_rejects_explicit_unready_target(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        cli_module,
        "probe_all_providers",
        lambda active=False: [probe("codex", state=ProviderState.AUTH_EXPIRED)],
    )

    result = runner.invoke(
        app,
        ["continue", "--path", str(tmp_path), "--target", "codex", "--dry-run"],
    )

    assert result.exit_code != 0
    assert "AUTH_EXPIRED" in result.stdout


def test_continue_falls_back_to_manual_when_all_ai_targets_unavailable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        cli_module,
        "probe_all_providers",
        lambda active=False: [
            probe("claude", state=ProviderState.LIMIT_REACHED),
            probe("codex", state=ProviderState.AUTH_EXPIRED),
            probe("manual", state=ProviderState.ALWAYS_READY, coding=False, repo=False, cloud=False, manual=True),
        ],
    )

    result = runner.invoke(app, ["continue", "--path", str(tmp_path), "--dry-run"])

    assert result.exit_code == 0
    assert "Manual continuation is still available" in result.stdout
    assert "everstate packet" in result.stdout


def test_continue_active_health_is_opt_in(monkeypatch, tmp_path: Path) -> None:
    seen: dict[str, bool] = {}

    def fake_probe_all_providers(*, active: bool = False):
        seen["active"] = active
        return [probe("codex")]

    monkeypatch.setattr(cli_module, "probe_all_providers", fake_probe_all_providers)
    result = runner.invoke(
        app,
        ["continue", "--path", str(tmp_path), "--active-health", "--dry-run"],
    )

    assert result.exit_code == 0
    assert seen["active"] is True


def test_continue_audits_failed_provider_and_offers_next_target(monkeypatch, tmp_path: Path) -> None:
    class FakeService:
        def continuation_packet(self, path: Path) -> ContinuationPacket:
            return packet()

    monkeypatch.setattr(cli_module, "_service", lambda: FakeService())
    monkeypatch.setattr(
        cli_module,
        "probe_all_providers",
        lambda active=False: [
            probe("codex"),
            probe("claude"),
            probe("manual", state=ProviderState.ALWAYS_READY, coding=False, repo=False, cloud=False, manual=True),
        ],
    )
    monkeypatch.setattr(
        cli_module,
        "launch_handoff",
        lambda root, packet, provider: HandoffResult(
            path=root / ".everstate" / "handoffs" / "test.md",
            command=[provider.executable, "prompt"],
            launched=True,
            returncode=1,
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "probe_executable_provider",
        lambda key, provider, active=False: probe(key, state=ProviderState.AUTH_EXPIRED),
    )

    result = runner.invoke(
        app,
        ["continue", "--path", str(tmp_path), "--target", "codex", "--yes"],
        input="n\n",
    )

    assert result.exit_code == 0
    assert "codex could not continue: AUTH_EXPIRED" in result.stdout
    assert "Next available fallback" in result.stdout
    assert "claude" in result.stdout
    assert "Fallback cancelled" in result.stdout
    history = tmp_path / ".everstate" / "routing-history.jsonl"
    assert history.exists()
    text = history.read_text(encoding="utf-8")
    assert '"target_key": "codex"' in text
    assert '"failure_class": "AUTH_EXPIRED"' in text
