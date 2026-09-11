from __future__ import annotations

import json
import urllib.error

import pytest

from everstate.freellmapi_fabric import FreeLLMAPIConfig, FreeLLMAPIError, FreeLLMAPIFabric


class FakeResponse:
    def __init__(self, payload) -> None:
        self._payload = payload

    def read(self) -> bytes:
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")


def test_config_reads_env_and_hides_secret(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EVERSTATE_HOME", str(tmp_path))
    monkeypatch.setenv("EVERSTATE_FREELLMAPI_URL", "http://localhost:3001/v1")
    monkeypatch.setenv("EVERSTATE_FREELLMAPI_API_KEY", "secret")
    config = FreeLLMAPIConfig.from_env()
    assert config.base_url == "http://localhost:3001/v1"
    assert config.api_key == "secret"
    assert "secret" not in repr(config)


def test_models_endpoint_uses_ready_filter_and_prefers_virtual_auto_target() -> None:
    captured = {}

    def opener(request, *, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        return FakeResponse({"data": [{"id": "z-model"}, {"id": "auto"}, {"id": "a-model"}]})

    fabric = FreeLLMAPIFabric(
        FreeLLMAPIConfig(base_url="http://127.0.0.1:3001/v1", api_key="unified"),
        opener=opener,
    )
    targets = fabric.discover_targets()
    assert captured["url"] == "http://127.0.0.1:3001/v1/models?ready=true"
    assert captured["authorization"] == "Bearer unified"
    assert [target.id for target in targets] == ["auto", "a-model", "z-model"]


def test_health_requires_currently_servable_models() -> None:
    def opener(request, *, timeout):
        assert request.full_url.endswith("/models?ready=true")
        return FakeResponse({"data": []})

    health = FreeLLMAPIFabric(opener=opener).health()
    assert health.ready is False
    assert health.status == "DEGRADED"
    assert "currently servable" in health.detail


def test_execute_is_openai_compatible() -> None:
    captured = {}

    def opener(request, *, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"choices": [{"message": {"content": "continued"}}]})

    fabric = FreeLLMAPIFabric(opener=opener)
    response = fabric.execute(model="auto", messages=[{"role": "user", "content": "continue"}])
    assert captured["body"]["model"] == "auto"
    assert captured["body"]["stream"] is False
    assert response.content == "continued"


def test_health_reports_transport_failure_without_crashing() -> None:
    def opener(request, *, timeout):
        raise urllib.error.URLError("connection refused")

    health = FreeLLMAPIFabric(opener=opener).health()
    assert health.ready is False
    assert health.status == "UNAVAILABLE"


def test_execute_rejects_missing_message_content() -> None:
    def opener(request, *, timeout):
        return FakeResponse({"choices": [{}]})

    with pytest.raises(FreeLLMAPIError, match="missing message content"):
        FreeLLMAPIFabric(opener=opener).execute(model="auto", messages=[{"role": "user", "content": "x"}])
