from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

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
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    active_check: bool = False

    @property
    def ready(self) -> bool:
        return self.state in {ProviderState.READY, ProviderState.ALWAYS_READY}


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part for part in [result.stdout, result.stderr] if part).strip()


def classify_provider_failure(output: str, returncode: int) -> ProviderState:
    text = output.lower()

    if "refresh token was already used" in text or "refresh_token_reused" in text or "token expired" in text or "token_revoked" in text:
        return ProviderState.AUTH_EXPIRED
    if "please log out and sign in again" in text or "authentication token" in text and "unauthorized" in text:
        return ProviderState.AUTH_EXPIRED
    if (
        "not logged in" in text
        or "not signed in" in text
        or "please log in" in text
        or "please sign in" in text
        or "please set an auth method" in text
        or "manual authorization is required" in text
        or "must specify the gemini_api_key" in text
        or "no authentication is configured" in text
    ):
        return ProviderState.NEEDS_LOGIN
    if (
        "usage limit" in text
        or "limit reached" in text
        or "quota exhausted" in text
        or "quota_exhausted" in text
        or "quota exceeded" in text
    ):
        return ProviderState.LIMIT_REACHED
    if "rate limit" in text or "too many requests" in text or "http 429" in text or "status 429" in text or "resource_exhausted" in text:
        return ProviderState.RATE_LIMITED
    if (
        "network is unreachable" in text
        or "connection refused" in text
        or "could not resolve host" in text
        or "temporary failure in name resolution" in text
        or "failed to connect" in text
        or "connection timed out" in text
    ):
        return ProviderState.NETWORK_UNAVAILABLE
    if "service unavailable" in text or "http 503" in text or "status 503" in text:
        return ProviderState.PROVIDER_OUTAGE
    if "model unavailable" in text or "model not found" in text or "unsupported model" in text:
        return ProviderState.MODEL_UNAVAILABLE
    if returncode != 0:
        return ProviderState.UNKNOWN_FAILURE
    return ProviderState.READY


def _run_probe(command: list[str], *, timeout: float = 12.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _auth_status_command(key: str, executable: str) -> list[str] | None:
    if key == "claude":
        return [executable, "auth", "status"]
    if key == "codex":
        return [executable, "login", "status"]
    return None


def _active_health_command(key: str, executable: str) -> list[str] | None:
    prompt = "Reply only EVERSTATE_READY. This is a provider health check; do not inspect files or tools."
    if key == "claude":
        return [executable, "-p", prompt]
    if key == "codex":
        return [
            executable,
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            prompt,
        ]
    if key == "gemini":
        return [executable, "-p", prompt, "--output-format", "json"]
    return None


def probe_executable_provider(
    key: str,
    provider: ProviderAdapter,
    *,
    active: bool = False,
) -> ProviderProbeResult:
    executable = provider.resolve_executable()
    capability = ProviderCapability(coding_agent=True, repository_access=True)
    if executable is None:
        return ProviderProbeResult(
            key=key,
            name=provider.name,
            state=ProviderState.NOT_INSTALLED,
            detail="Executable not found on PATH or known user install locations.",
            executable=None,
            capability=capability,
            active_check=active,
        )

    auth_command = _auth_status_command(key, executable)
    if auth_command is not None:
        auth_result = _run_probe(auth_command)
        if auth_result is None:
            return ProviderProbeResult(
                key=key,
                name=provider.name,
                state=ProviderState.UNKNOWN_FAILURE,
                detail="Local authentication status probe could not complete.",
                executable=executable,
                capability=capability,
                active_check=active,
            )
        auth_output = _combined_output(auth_result)
        if auth_result.returncode != 0:
            state = classify_provider_failure(auth_output, auth_result.returncode)
            if state is ProviderState.UNKNOWN_FAILURE:
                state = ProviderState.NEEDS_LOGIN
            return ProviderProbeResult(
                key=key,
                name=provider.name,
                state=state,
                detail=(auth_output[-500:] or "Provider reports that authentication is not ready."),
                executable=executable,
                capability=capability,
                active_check=active,
            )

    if not active:
        passive_detail = (
            "Executable and local authentication status are ready; quota/network were not actively tested."
            if auth_command is not None
            else "Executable found; authentication/quota/network were not actively verified for this provider."
        )
        return ProviderProbeResult(
            key=key,
            name=provider.name,
            state=ProviderState.READY,
            detail=passive_detail,
            executable=executable,
            capability=capability,
            active_check=False,
        )

    health_command = _active_health_command(key, executable)
    if health_command is None:
        return ProviderProbeResult(
            key=key,
            name=provider.name,
            state=ProviderState.READY,
            detail="Executable/auth ready; no active health command is defined for this provider yet.",
            executable=executable,
            capability=capability,
            active_check=True,
        )

    with tempfile.TemporaryDirectory(prefix="everstate-provider-probe-") as temporary_directory:
        try:
            result = subprocess.run(
                health_command,
                cwd=Path(temporary_directory),
                check=False,
                capture_output=True,
                text=True,
                timeout=25.0,
            )
        except subprocess.TimeoutExpired:
            return ProviderProbeResult(
                key=key,
                name=provider.name,
                state=ProviderState.NETWORK_UNAVAILABLE,
                detail="Active provider health check timed out.",
                executable=executable,
                capability=capability,
                active_check=True,
            )
        except OSError as exc:
            return ProviderProbeResult(
                key=key,
                name=provider.name,
                state=ProviderState.UNKNOWN_FAILURE,
                detail=f"Active provider health check could not start: {exc}",
                executable=executable,
                capability=capability,
                active_check=True,
            )

    output = _combined_output(result)
    state = classify_provider_failure(output, result.returncode)
    if state is ProviderState.READY:
        detail = "Active provider health check succeeded."
    else:
        detail = output[-500:] or f"Provider health command exited with code {result.returncode}."
    return ProviderProbeResult(
        key=key,
        name=provider.name,
        state=state,
        detail=detail,
        executable=executable,
        capability=capability,
        active_check=True,
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


def probe_all_providers(*, active: bool = False) -> list[ProviderProbeResult]:
    results = [
        probe_executable_provider(key, provider, active=active)
        for key, provider in PROVIDERS.items()
    ]
    results.append(probe_manual_export())
    return results
