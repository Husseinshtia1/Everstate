from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from everstate.providers import ProviderAdapter, ProviderQuotaError


def test_automated_provider_raises_quota_error_without_hiding_output(tmp_path: Path, monkeypatch, capsys):
    provider = ProviderAdapter(
        name="Codex",
        executable="codex",
        automation_args=("exec",),
    )
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/usr/bin/codex")

    def fake_run(command, **kwargs):
        return SimpleNamespace(
            returncode=1,
            stdout="OpenAI Codex\n",
            stderr="ERROR: You've hit your usage limit. Purchase more credits or try again later.\n",
        )

    monkeypatch.setattr("everstate.providers.subprocess.run", fake_run)

    with pytest.raises(ProviderQuotaError, match="usage quota is exhausted"):
        provider.launch_automated(tmp_path, "do work")

    captured = capsys.readouterr()
    assert "OpenAI Codex" in captured.out
    assert "usage limit" in captured.err


def test_non_quota_failure_remains_a_normal_provider_exit(tmp_path: Path, monkeypatch):
    provider = ProviderAdapter(
        name="Codex",
        executable="codex",
        automation_args=("exec",),
    )
    monkeypatch.setattr(ProviderAdapter, "resolve_executable", lambda self: "/usr/bin/codex")
    monkeypatch.setattr(
        "everstate.providers.subprocess.run",
        lambda command, **kwargs: SimpleNamespace(returncode=7, stdout="", stderr="compile failed\n"),
    )

    assert provider.launch_automated(tmp_path, "do work") == 7
