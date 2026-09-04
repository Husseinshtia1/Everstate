from __future__ import annotations

from everstate.provider_readiness import ProviderState, probe_executable_provider, probe_manual_export
from everstate.providers import ProviderAdapter


def test_probe_marks_missing_provider_not_installed(monkeypatch) -> None:
    provider = ProviderAdapter(name="Missing", executable="definitely-missing-everstate-binary")

    monkeypatch.setattr(provider, "resolve_executable", lambda: None)
    result = probe_executable_provider("missing", provider)

    assert result.state is ProviderState.NOT_INSTALLED
    assert result.ready is False
    assert result.executable is None


def test_probe_marks_discovered_provider_ready(monkeypatch) -> None:
    provider = ProviderAdapter(name="Example", executable="example")

    monkeypatch.setattr(provider, "resolve_executable", lambda: "/tmp/example")
    result = probe_executable_provider("example", provider)

    assert result.state is ProviderState.READY
    assert result.ready is True
    assert result.executable == "/tmp/example"
    assert result.capability.coding_agent is True
    assert result.capability.repository_access is True


def test_manual_export_is_always_ready() -> None:
    result = probe_manual_export()

    assert result.state is ProviderState.ALWAYS_READY
    assert result.ready is True
    assert result.capability.manual is True
    assert result.capability.cloud is False
