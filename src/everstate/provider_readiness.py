from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .providers import PROVIDERS, ProviderAdapter


class ProviderState(StrEnum):
    READY = "READY"
    NOT_INSTALLED = "NOT_INSTALLED"
    NEEDS_LOGIN = "NEEDS_LOGIN"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    LIMIT_REACHED = "LIMIT_REACHED"
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    PROVIDER_OUTAGE = "PROVIDER_OUTAGE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    LOCAL_MODEL_MISSING = "LOCAL_MODEL_MISSING"
    LOCAL_RESOURCE_INSUFFICIENT = "LOCAL_RESOURCE_INSUFFICIENT"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"
    ALWAYS_READY = "ALWAYS_READY"


@dataclass(frozen=True)
class ProviderCapability:
    coding_agent: bool = False
    repository_access: bool = False
    local: bool = False
    cloud: bool = True
    manual: bool = False


@dataclass(frozen=True)
class ProviderProbeResult:
    key: str
    name: str
    state: ProviderState
    detail: str
    executable: str | None
    capability: ProviderCapability

    @property
    def ready(self) -> bool:
        return self.state in {ProviderState.READY, ProviderState.ALWAYS_READY}


def probe_executable_provider(key: str, provider: ProviderAdapter) -> ProviderProbeResult:
    executable = provider.resolve_executable()
    if executable is None:
        return ProviderProbeResult(
            key=key,
            name=provider.name,
            state=ProviderState.NOT_INSTALLED,
            detail="Executable not found on PATH or known user install locations.",
            executable=None,
            capability=ProviderCapability(coding_agent=True, repository_access=True),
        )
    return ProviderProbeResult(
        key=key,
        name=provider.name,
        state=ProviderState.READY,
        detail="Executable discovered. Authentication/quota health has not yet been verified.",
        executable=executable,
        capability=ProviderCapability(coding_agent=True, repository_access=True),
    )


def probe_manual_export() -> ProviderProbeResult:
    return ProviderProbeResult(
        key="manual",
        name="Manual export",
        state=ProviderState.ALWAYS_READY,
        detail="Portable Markdown/JSON continuation remains available without an AI provider.",
        executable=None,
        capability=ProviderCapability(cloud=False, manual=True),
    )


def probe_all_providers() -> list[ProviderProbeResult]:
    results = [probe_executable_provider(key, provider) for key, provider in PROVIDERS.items()]
    results.append(probe_manual_export())
    return results
