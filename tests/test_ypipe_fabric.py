from __future__ import annotations

import json
import urllib.error
from dataclasses import dataclass

import pytest

from everstate.ypipe_fabric import YpipeConfig, YpipeError, YpipeFabric, YpipeMcpClient


@dataclass
class FakeResponse:
    payload: bytes

    def read(self) -> bytes:
        return self.payload


def _json_response(value: dict) -> FakeResponse:
    return FakeResponse(json.dumps(value).encode("utf-8"))


def test_config_hides_api_key_from_repr() -> None:
    config = YpipeConfig(api_key="secret-token")
    assert "secret-token" not in repr(config)


def test_remote_endpoint_rejected_by_default() -> None:
    with pytest.raises(ValueError, match="local-only"):
        YpipeFabric(YpipeConfig(base_url="https://example.com/v1"))


def test_remote_endpoint_can_be_explicitly_enabled() -> None:
    fabric = YpipeFabric(YpipeConfig(base_url="https://example.com/v1", allow_remote=True))
    assert fabric.name == "ypipe"


def test_discover_targets_uses_openai_models_contract() -> None:
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return _json_response(
            {
                "object": "list",
                "data": [
                    {"id": "system/qwen", "owned_by": "ypipe"},
                    {"id": "local/reasoner"},
                    {"id": ""},
                ],
            }
        )

    fabric = YpipeFabric(YpipeConfig(base_url="http://127.0.0.1:4000/v1"), opener=opener)
    targets = fabric.discover_targets()
    assert seen["url"] == "http://127.0.0.1:4000/v1/models"
    assert [target.id for target in targets] == ["system/qwen", "local/reasoner"]
    assert targets[0].provider == "ypipe"
    assert targets[1].provider == "ypipe-local"


def test_health_ready_only_when_local_models_exist() -> None:
    fabric = YpipeFabric(
        YpipeConfig(),
        opener=lambda request, timeout: _json_response({"data": [{"id": "system/qwen"}]}),
    )
    health = fabric.health()
    assert health.ready is True
    assert health.status == "READY"


def test_health_degraded_when_models_empty() -> None:
    fabric = YpipeFabric(YpipeConfig(), opener=lambda request, timeout: _json_response({"data": []}))
    health = fabric.health()
    assert health.ready is False
    assert health.status == "DEGRADED"


def test_health_unavailable_on_transport_failure() -> None:
    def opener(request, timeout):
        raise urllib.error.URLError("offline")

    fabric = YpipeFabric(YpipeConfig(), opener=opener)
    health = fabric.health()
    assert health.ready is False
    assert health.status == "UNAVAILABLE"


def test_execute_uses_chat_completions_contract_and_bearer_auth() -> None:
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return _json_response(
            {"choices": [{"message": {"role": "assistant", "content": "LOCAL_OK"}}]}
        )

    fabric = YpipeFabric(YpipeConfig(api_key="top-secret"), opener=opener)
    response = fabric.execute(model="system/qwen", messages=[{"role": "user", "content": "ping"}])
    assert response.content == "LOCAL_OK"
    assert seen["url"].endswith("/v1/chat/completions")
    assert seen["headers"]["Authorization"] == "Bearer top-secret"
    assert seen["body"] == {
        "model": "system/qwen",
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
    }


def test_execute_rejects_malformed_chat_response() -> None:
    fabric = YpipeFabric(YpipeConfig(), opener=lambda request, timeout: _json_response({"choices": []}))
    with pytest.raises(YpipeError, match="missing choices"):
        fabric.execute(model="m", messages=[{"role": "user", "content": "x"}])


def test_smartpipe_relative_endpoint_uses_ypipe_origin_not_v1_prefix() -> None:
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return _json_response({"status": "ok"})

    fabric = YpipeFabric(YpipeConfig(base_url="http://localhost:4000/v1"), opener=opener)
    result = fabric.run_smartpipe("api/triage", {"ticket": "x"})
    assert result == {"status": "ok"}
    assert seen["url"] == "http://localhost:4000/api/triage"
    assert seen["body"] == {"ticket": "x"}


def test_smartpipe_remote_endpoint_rejected_by_default() -> None:
    fabric = YpipeFabric(YpipeConfig())
    with pytest.raises(ValueError, match="must stay local"):
        fabric.run_smartpipe("https://example.com/triage", {})


def test_mcp_json_response_supports_initialize_list_and_call() -> None:
    seen_methods = []

    def opener(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        seen_methods.append(payload["method"])
        if payload["method"] == "initialize":
            result = {"protocolVersion": "2025-11-25", "capabilities": {}}
        elif payload["method"] == "tools/list":
            result = {"tools": [{"name": "read_file"}]}
        else:
            result = {"content": [{"type": "text", "text": "ok"}]}
        return _json_response({"jsonrpc": "2.0", "id": payload["id"], "result": result})

    client = YpipeMcpClient("http://localhost:12001/mcp", opener=opener)
    assert client.initialize()["protocolVersion"] == "2025-11-25"
    assert client.list_tools() == ({"name": "read_file"},)
    assert client.call_tool("read_file", {"path": "README.md"})["content"][0]["text"] == "ok"
    assert seen_methods == ["initialize", "tools/list", "tools/call"]


def test_mcp_sse_data_envelope_is_supported() -> None:
    def opener(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        body = (
            "event: message\n"
            + "data: "
            + json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": {"tools": []}})
            + "\n\n"
        )
        return FakeResponse(body.encode("utf-8"))

    client = YpipeMcpClient("http://127.0.0.1:12001/mcp", opener=opener)
    assert client.list_tools() == ()


def test_mcp_remote_endpoint_rejected_by_default() -> None:
    with pytest.raises(ValueError, match="must be local"):
        YpipeMcpClient("https://example.com/mcp")
