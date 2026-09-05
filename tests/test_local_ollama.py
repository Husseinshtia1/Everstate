from __future__ import annotations

import json

import everstate.local_ollama as local_ollama
from everstate.local_ollama import model_is_installed, probe_ollama_runtime


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_local_ollama_discovers_installed_models(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.setattr(
        local_ollama,
        "urlopen",
        lambda request, timeout=2.0: FakeResponse(
            {"models": [{"name": "gpt-oss:20b"}, {"model": "qwen3-coder:latest"}]}
        ),
    )

    status = probe_ollama_runtime()

    assert status.reachable is True
    assert status.base_url == "http://127.0.0.1:11434"
    assert status.models == ("gpt-oss:20b", "qwen3-coder:latest")


def test_nonlocal_ollama_host_is_not_probed_as_local(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://192.0.2.10:11434")
    called = {"value": False}

    def fake_urlopen(*args, **kwargs):
        called["value"] = True
        raise AssertionError("remote Ollama host must not be probed by local fallback")

    monkeypatch.setattr(local_ollama, "urlopen", fake_urlopen)
    status = probe_ollama_runtime()

    assert status.reachable is False
    assert "non-local host" in status.detail
    assert called["value"] is False


def test_model_matching_accepts_explicit_latest_tag() -> None:
    assert model_is_installed("qwen3-coder", ("qwen3-coder:latest",)) is True
    assert model_is_installed("gpt-oss:20b", ("gpt-oss:20b",)) is True
    assert model_is_installed("missing", ("gpt-oss:20b",)) is False
