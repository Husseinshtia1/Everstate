from __future__ import annotations

import subprocess

import everstate.provider_readiness as readiness
from everstate.local_ollama import OllamaRuntimeStatus
from everstate.provider_readiness import (
    ProviderState,
    classify_provider_failure,
    probe_codex_ollama,
    probe_executable_provider,
    probe_manual_export,
)
from everstate.providers import ProviderAdapter


def test_probe_marks_missing_provider_not_installed(monkeypatch) -> None:
    provider = ProviderAdapter(name="Missing", executable="definitely-missing-everstate-binary")
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: None)
    result = probe_executable_provider("missing", provider)
    assert result.state is ProviderState.NOT_INSTALLED
    assert result.ready is False
    assert result.executable is None


def test_probe_marks_discovered_unknown_provider_ready_without_auth_probe(monkeypatch) -> None:
    provider = ProviderAdapter(name="Example", executable="example")
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/tmp/example")
    result = probe_executable_provider("example", provider)
    assert result.state is ProviderState.READY
    assert result.ready is True
    assert result.executable == "/tmp/example"
    assert result.active_check is False
    assert result.capability.coding_agent is True
    assert result.capability.repository_access is True


def test_passive_codex_probe_detects_missing_login(monkeypatch) -> None:
    provider = ProviderAdapter(name="Codex", executable="codex")
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/tmp/codex")
    monkeypatch.setattr(
        readiness,
        "_run_probe",
        lambda command, timeout=12.0: subprocess.CompletedProcess(command, 1, stdout="Not logged in", stderr=""),
    )
    result = probe_executable_provider("codex", provider)
    assert result.state is ProviderState.NEEDS_LOGIN
    assert result.ready is False


def test_passive_claude_probe_verifies_local_auth_without_spending_quota(monkeypatch) -> None:
    provider = ProviderAdapter(name="Claude Code", executable="claude")
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/tmp/claude")
    monkeypatch.setattr(
        readiness,
        "_run_probe",
        lambda command, timeout=12.0: subprocess.CompletedProcess(command, 0, stdout='{"loggedIn":true}', stderr=""),
    )
    result = probe_executable_provider("claude", provider)
    assert result.state is ProviderState.READY
    assert result.ready is True
    assert "quota/network were not actively tested" in result.detail


def test_passive_gemini_probe_is_truthful_about_unverified_auth(monkeypatch) -> None:
    provider = ProviderAdapter(name="Gemini CLI", executable="gemini", prompt_args=("-i",))
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/tmp/gemini")
    result = probe_executable_provider("gemini", provider)
    assert result.state is ProviderState.READY
    assert result.ready is True
    assert "authentication/quota/network were not actively verified" in result.detail


def local_provider() -> ProviderAdapter:
    return ProviderAdapter(
        name="Codex + Ollama (local)",
        executable="codex",
        prompt_args=("--oss", "--local-provider", "ollama"),
        model_env="EVERSTATE_OLLAMA_MODEL",
        default_model="gpt-oss:20b",
    )


def test_local_codex_requires_codex_frontend(monkeypatch) -> None:
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: None)
    result = probe_codex_ollama(local_provider())
    assert result.state is ProviderState.NOT_INSTALLED
    assert result.capability.local is True
    assert result.capability.cloud is False


def test_local_codex_distinguishes_unavailable_ollama_runtime(monkeypatch) -> None:
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/tmp/codex")
    monkeypatch.setattr(
        readiness,
        "probe_ollama_runtime",
        lambda: OllamaRuntimeStatus(False, (), "Ollama local API is not reachable", "http://127.0.0.1:11434"),
    )
    result = probe_codex_ollama(local_provider())
    assert result.state is ProviderState.LOCAL_RUNTIME_UNAVAILABLE
    assert result.ready is False


def test_local_codex_never_auto_downloads_missing_model(monkeypatch) -> None:
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/tmp/codex")
    monkeypatch.setattr(
        readiness,
        "probe_ollama_runtime",
        lambda: OllamaRuntimeStatus(True, ("qwen3-coder:latest",), "ready", "http://127.0.0.1:11434"),
    )
    result = probe_codex_ollama(local_provider())
    assert result.state is ProviderState.LOCAL_MODEL_MISSING
    assert "will not pull a model automatically" in result.detail


def test_local_codex_is_ready_only_when_selected_model_is_already_installed(monkeypatch) -> None:
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/tmp/codex")
    monkeypatch.setattr(
        readiness,
        "probe_ollama_runtime",
        lambda: OllamaRuntimeStatus(True, ("gpt-oss:20b",), "ready", "http://127.0.0.1:11434"),
    )
    result = probe_codex_ollama(local_provider())
    assert result.state is ProviderState.READY
    assert result.ready is True
    assert result.capability.local is True
    assert "No model request was sent" in result.detail


def test_active_local_probe_classifies_insufficient_memory(monkeypatch) -> None:
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/tmp/codex")
    monkeypatch.setattr(
        readiness,
        "probe_ollama_runtime",
        lambda: OllamaRuntimeStatus(True, ("gpt-oss:20b",), "ready", "http://127.0.0.1:11434"),
    )
    seen: dict[str, list[str]] = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="model requires more system memory")

    monkeypatch.setattr(readiness.subprocess, "run", fake_run)
    result = probe_codex_ollama(local_provider(), active=True)
    assert result.state is ProviderState.LOCAL_RESOURCE_INSUFFICIENT
    assert result.ready is False
    assert seen["command"][:5] == ["/tmp/codex", "exec", "--oss", "--local-provider", "ollama"]
    assert "-m" in seen["command"]
    assert "gpt-oss:20b" in seen["command"]


def test_active_probe_classifies_real_refresh_token_failure(monkeypatch) -> None:
    provider = ProviderAdapter(name="Codex", executable="codex")
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/tmp/codex")
    monkeypatch.setattr(
        readiness,
        "_run_probe",
        lambda command, timeout=12.0: subprocess.CompletedProcess(command, 0, stdout="Logged in using ChatGPT", stderr=""),
    )

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.",
        )

    monkeypatch.setattr(readiness.subprocess, "run", fake_run)
    result = probe_executable_provider("codex", provider, active=True)
    assert result.state is ProviderState.AUTH_EXPIRED
    assert result.ready is False
    assert result.active_check is True


def test_active_gemini_probe_uses_headless_prompt_and_classifies_missing_auth(monkeypatch) -> None:
    provider = ProviderAdapter(name="Gemini CLI", executable="gemini", prompt_args=("-i",))
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/tmp/gemini")
    seen: dict[str, list[str]] = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="Please set an Auth method before running Gemini CLI")

    monkeypatch.setattr(readiness.subprocess, "run", fake_run)
    result = probe_executable_provider("gemini", provider, active=True)
    assert result.state is ProviderState.NEEDS_LOGIN
    assert result.ready is False
    assert result.active_check is True
    assert seen["command"][:2] == ["/tmp/gemini", "-p"]
    assert "--output-format" in seen["command"]
    assert "json" in seen["command"]


def test_failure_classifier_distinguishes_limits_rate_network_and_local_memory() -> None:
    assert classify_provider_failure("Usage limit reached", 1) is ProviderState.LIMIT_REACHED
    assert classify_provider_failure("QUOTA_EXHAUSTED", 1) is ProviderState.LIMIT_REACHED
    assert classify_provider_failure("HTTP 429 Too Many Requests", 1) is ProviderState.RATE_LIMITED
    assert classify_provider_failure("RESOURCE_EXHAUSTED", 1) is ProviderState.RATE_LIMITED
    assert classify_provider_failure("connection refused", 1) is ProviderState.NETWORK_UNAVAILABLE
    assert classify_provider_failure("HTTP 503 Service Unavailable", 1) is ProviderState.PROVIDER_OUTAGE
    assert classify_provider_failure("out of memory", 1) is ProviderState.LOCAL_RESOURCE_INSUFFICIENT


def test_manual_export_is_always_ready() -> None:
    result = probe_manual_export()
    assert result.state is ProviderState.ALWAYS_READY
    assert result.ready is True
    assert result.capability.manual is True
    assert result.capability.cloud is False
