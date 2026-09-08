from __future__ import annotations

import everstate.provider_readiness as readiness
from everstate.omniroute_fabric import OmniRouteError
from everstate.provider_fabric import FabricTarget
from everstate.provider_readiness import ProviderState, probe_codex_omniroute
from everstate.providers import ProviderAdapter, get_provider


def _resolve_cli(self: ProviderAdapter) -> str | None:
    if self.executable == "omniroute":
        return "/tmp/omniroute"
    if self.executable == "codex":
        return "/tmp/codex"
    return None


def test_codex_omniroute_builds_launcher_command_with_model(monkeypatch) -> None:
    monkeypatch.setenv("EVERSTATE_OMNIROUTE_MODEL", "glm/glm-5.2")
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", _resolve_cli)

    provider = get_provider("codex-omniroute")
    command = provider.interactive_command("CONTINUE")

    assert command == [
        "/tmp/omniroute",
        "run",
        "codex",
        "--model",
        "glm/glm-5.2",
        "--",
        "CONTINUE",
    ]
    assert provider.handoff_name == "codex-omniroute"


def test_codex_omniroute_builds_launcher_command_without_forcing_model(monkeypatch) -> None:
    monkeypatch.delenv("EVERSTATE_OMNIROUTE_MODEL", raising=False)
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", _resolve_cli)

    provider = get_provider("codex-omniroute")

    assert provider.interactive_command("CONTINUE") == [
        "/tmp/omniroute",
        "run",
        "codex",
        "--",
        "CONTINUE",
    ]


def test_passive_probe_requires_both_omniroute_and_codex(monkeypatch) -> None:
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", _resolve_cli)

    result = probe_codex_omniroute(get_provider("codex-omniroute"), active=False)

    assert result.state is ProviderState.READY
    assert result.ready is True
    assert result.capability.coding_agent is True
    assert result.capability.repository_access is True
    assert "not actively tested" in result.detail


def test_probe_fails_when_codex_frontend_is_missing(monkeypatch) -> None:
    def resolve(self: ProviderAdapter) -> str | None:
        return "/tmp/omniroute" if self.executable == "omniroute" else None

    monkeypatch.setattr(ProviderAdapter, "resolve_executable", resolve)

    result = probe_codex_omniroute(get_provider("codex-omniroute"), active=True)

    assert result.state is ProviderState.NOT_INSTALLED
    assert result.ready is False
    assert "Codex CLI is required" in result.detail


def test_active_probe_verifies_live_catalog_and_selected_model(monkeypatch) -> None:
    monkeypatch.setenv("EVERSTATE_OMNIROUTE_MODEL", "glm/glm-5.2")
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", _resolve_cli)

    class FakeFabric:
        def discover_targets(self):
            return (
                FabricTarget(id="glm/glm-5.2", provider="glm", model="glm/glm-5.2"),
                FabricTarget(id="cx/gpt-5.5", provider="codex", model="cx/gpt-5.5"),
            )

    monkeypatch.setattr(readiness, "OmniRouteFabric", FakeFabric)

    result = probe_codex_omniroute(get_provider("codex-omniroute"), active=True)

    assert result.state is ProviderState.READY
    assert result.ready is True
    assert result.active_check is True
    assert "2 model target" in result.detail
    assert "glm/glm-5.2" in result.detail


def test_active_probe_rejects_configured_model_missing_from_catalog(monkeypatch) -> None:
    monkeypatch.setenv("EVERSTATE_OMNIROUTE_MODEL", "missing/model")
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", _resolve_cli)

    class FakeFabric:
        def discover_targets(self):
            return (FabricTarget(id="cx/gpt-5.5", provider="codex", model="cx/gpt-5.5"),)

    monkeypatch.setattr(readiness, "OmniRouteFabric", FakeFabric)

    result = probe_codex_omniroute(get_provider("codex-omniroute"), active=True)

    assert result.state is ProviderState.MODEL_UNAVAILABLE
    assert result.ready is False
    assert "missing/model" in result.detail


def test_active_probe_maps_gateway_failure_without_launching_codex(monkeypatch) -> None:
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", _resolve_cli)

    class FakeFabric:
        def discover_targets(self):
            raise OmniRouteError("connection refused")

    monkeypatch.setattr(readiness, "OmniRouteFabric", FakeFabric)

    result = probe_codex_omniroute(get_provider("codex-omniroute"), active=True)

    assert result.state is ProviderState.NETWORK_UNAVAILABLE
    assert result.ready is False
    assert "connection refused" in result.detail
