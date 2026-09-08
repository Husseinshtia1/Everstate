from __future__ import annotations

import json
import urllib.error

import pytest

from everstate.omniroute_fabric import OmniRouteConfig, OmniRouteError, OmniRouteFabric


class FakeResponse:
    def __init__(self, payload) -> None:
        self._payload = payload

    def read(self) -> bytes:
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")


def test_config_reads_environment_without_exposing_secret(monkeypatch) -> None:
    monkeypatch.setenv("EVERSTATE_OMNIROUTE_URL", "http://localhost:9999/v1")
    monkeypatch.setenv("EVERSTATE_OMNIROUTE_API_KEY", "top-secret")
    monkeypatch.setenv("EVERSTATE_OMNIROUTE_TIMEOUT", "7.5")

    config = OmniRouteConfig.from_env()

    assert config.base_url == "http://localhost:9999/v1"
    assert config.api_key == "top-secret"
    assert config.timeout == 7.5
    assert "top-secret" not in repr(config)


def test_config_rejects_invalid_timeout(monkeypatch) -> None:
    monkeypatch.setenv("EVERSTATE_OMNIROUTE_TIMEOUT", "invalid")
    with pytest.raises(ValueError, match="must be a number"):
        OmniRouteConfig.from_env()


def test_fabric_rejects_non_http_url() -> None:
    with pytest.raises(ValueError, match="absolute http"):
        OmniRouteFabric(OmniRouteConfig(base_url="file:///tmp/socket"))


def test_discover_targets_uses_models_endpoint_and_auth_header() -> None:
    captured = {}

    def opener(request, *, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "data": [
                    {"id": "model-a", "owned_by": "provider-a"},
                    {"id": "model-b"},
                    {"owned_by": "ignored"},
                ]
            }
        )

    fabric = OmniRouteFabric(
        OmniRouteConfig(
            base_url="http://127.0.0.1:20128/v1/",
            api_key="secret",
            timeout=4.0,
        ),
        opener=opener,
    )

    targets = fabric.discover_targets()

    assert captured == {
        "url": "http://127.0.0.1:20128/v1/models",
        "authorization": "Bearer secret",
        "timeout": 4.0,
    }
    assert [target.id for target in targets] == ["model-a", "model-b"]
    assert targets[0].provider == "provider-a"
    assert targets[1].provider is None


def test_health_is_ready_when_models_are_available() -> None:
    def opener(request, *, timeout):
        return FakeResponse({"data": [{"id": "model-a"}]})

    health = OmniRouteFabric(opener=opener).health()

    assert health.ready is True
    assert health.status == "READY"
    assert "1 model target" in health.detail


def test_health_is_degraded_when_gateway_has_no_models() -> None:
    def opener(request, *, timeout):
        return FakeResponse({"data": []})

    health = OmniRouteFabric(opener=opener).health()

    assert health.ready is False
    assert health.status == "DEGRADED"


def test_health_is_unavailable_on_transport_failure() -> None:
    def opener(request, *, timeout):
        raise urllib.error.URLError("connection refused")

    health = OmniRouteFabric(opener=opener).health()

    assert health.ready is False
    assert health.status == "UNAVAILABLE"
    assert "connection refused" in health.detail


def test_execute_sends_openai_compatible_chat_request() -> None:
    captured = {}

    def opener(request, *, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse(
            {"choices": [{"message": {"role": "assistant", "content": "continued"}}]}
        )

    fabric = OmniRouteFabric(
        OmniRouteConfig(base_url="http://localhost:20128/v1", timeout=2.0),
        opener=opener,
    )
    response = fabric.execute(
        model="coding-target",
        messages=[{"role": "user", "content": "continue the project"}],
        timeout=9.0,
    )

    assert captured["url"] == "http://localhost:20128/v1/chat/completions"
    assert captured["method"] == "POST"
    assert captured["timeout"] == 9.0
    assert captured["body"] == {
        "model": "coding-target",
        "messages": [{"role": "user", "content": "continue the project"}],
        "stream": False,
    }
    assert response.target == "coding-target"
    assert response.content == "continued"


def test_execute_rejects_missing_content() -> None:
    def opener(request, *, timeout):
        return FakeResponse({"choices": [{}]})

    fabric = OmniRouteFabric(opener=opener)

    with pytest.raises(OmniRouteError, match="missing message content"):
        fabric.execute(model="model-a", messages=[{"role": "user", "content": "x"}])


def test_request_rejects_invalid_json() -> None:
    def opener(request, *, timeout):
        return FakeResponse(b"not-json")

    fabric = OmniRouteFabric(opener=opener)

    with pytest.raises(OmniRouteError, match="invalid JSON"):
        fabric.discover_targets()
