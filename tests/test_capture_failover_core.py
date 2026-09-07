from __future__ import annotations

import json
from pathlib import Path

from everstate.capture import CaptureEngine
from everstate.emergency_failover import prepare_emergency_failover
from everstate.mcp_server import LATEST_PROTOCOL, handle_request
from everstate.service import EverstateService
from everstate.storage import LocalStore


def _engine(tmp_path: Path) -> CaptureEngine:
    return CaptureEngine(EverstateService(LocalStore(tmp_path / "everstate.db")))


def _modern_meta() -> dict:
    return {
        "io.modelcontextprotocol/protocolVersion": LATEST_PROTOCOL,
        "io.modelcontextprotocol/clientInfo": {"name": "claude-probe", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }


def test_mcp_2026_server_discover_is_conformant() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": "discover-1",
            "method": "server/discover",
            "params": {"_meta": _modern_meta()},
        }
    )
    assert response is not None
    result = response["result"]
    assert result["resultType"] == "complete"
    assert LATEST_PROTOCOL in result["supportedVersions"]
    assert result["capabilities"] == {"tools": {}}
    assert result["cacheScope"] == "private"
    assert result["ttlMs"] == 60000
    assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "everstate-capture"


def test_mcp_2026_tools_list_and_call_have_modern_result_shape(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    engine = _engine(tmp_path)

    listed = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {"_meta": _modern_meta()},
        },
        engine,
    )
    assert listed is not None
    assert listed["result"]["resultType"] == "complete"
    assert listed["result"]["cacheScope"] == "private"
    assert {tool["name"] for tool in listed["result"]["tools"]} == {
        "everstate_capture",
        "everstate_status",
    }

    called = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "_meta": _modern_meta(),
                "name": "everstate_capture",
                "arguments": {
                    "project_root": str(root),
                    "kind": "task",
                    "value": "MODERN_CAPTURE",
                    "source_provider": "claude-desktop",
                },
            },
        },
        engine,
    )
    assert called is not None
    assert called["result"]["resultType"] == "complete"
    assert called["result"]["isError"] is False
    assert engine.service.status(root).current_task == "MODERN_CAPTURE"


def test_mcp_legacy_initialize_and_tools_list_remain_compatible() -> None:
    initialized = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "legacy", "version": "1"},
            },
        }
    )
    assert initialized is not None
    assert initialized["result"]["protocolVersion"] == "2025-11-25"

    notification = handle_request(
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    )
    assert notification is None

    listed = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert listed is not None
    assert "resultType" not in listed["result"]
    assert {tool["name"] for tool in listed["result"]["tools"]} == {
        "everstate_capture",
        "everstate_status",
    }


def test_multi_project_capture_is_isolated(tmp_path: Path) -> None:
    a = tmp_path / "project-a"
    b = tmp_path / "project-b"
    a.mkdir()
    b.mkdir()
    engine = _engine(tmp_path)

    engine.capture(root=a, kind="objective", value="OBJECTIVE_A_ONLY", source_provider="claude")
    engine.capture(root=a, kind="constraint", value="NEVER_B", source_provider="claude")
    engine.capture(root=b, kind="objective", value="OBJECTIVE_B_ONLY", source_provider="claude")
    engine.capture(root=b, kind="constraint", value="NEVER_A", source_provider="claude")

    state_a = engine.service.status(a)
    state_b = engine.service.status(b)

    assert state_a.project_id != state_b.project_id
    assert state_a.objective == "OBJECTIVE_A_ONLY"
    assert state_b.objective == "OBJECTIVE_B_ONLY"
    assert state_a.active_constraints == ["NEVER_B"]
    assert state_b.active_constraints == ["NEVER_A"]
    assert "OBJECTIVE_B_ONLY" not in state_a.model_dump_json()
    assert "OBJECTIVE_A_ONLY" not in state_b.model_dump_json()


def test_mcp_capture_tool_updates_canonical_state(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    engine = _engine(tmp_path)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "everstate_capture",
                "arguments": {
                    "project_root": str(root),
                    "kind": "next_action",
                    "value": "RUN_ACCEPTANCE_GATE",
                    "source_provider": "claude",
                    "source_session": "session-test",
                },
            },
        },
        engine,
    )

    assert response is not None
    assert response["result"]["isError"] is False
    assert engine.service.status(root).next_action == "RUN_ACCEPTANCE_GATE"


def test_mcp_allowed_root_rejects_cross_project_capture(tmp_path: Path, monkeypatch) -> None:
    allowed = tmp_path / "allowed"
    other = tmp_path / "other"
    allowed.mkdir()
    other.mkdir()
    engine = _engine(tmp_path)
    monkeypatch.setenv("EVERSTATE_ALLOWED_ROOT", str(allowed))

    blocked = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {
                "name": "everstate_capture",
                "arguments": {
                    "project_root": str(other),
                    "kind": "objective",
                    "value": "MUST_NOT_BE_WRITTEN",
                    "source_provider": "claude",
                },
            },
        },
        engine,
    )
    assert blocked is not None
    assert blocked["result"]["isError"] is True
    assert "outside the configured Everstate MCP boundary" in blocked["result"]["content"][0]["text"]
    assert engine.service.store.get_project_by_root(other) is None

    allowed_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {
                "name": "everstate_capture",
                "arguments": {
                    "project_root": str(allowed),
                    "kind": "objective",
                    "value": "ALLOWED_STATE",
                    "source_provider": "claude",
                },
            },
        },
        engine,
    )
    assert allowed_response is not None
    assert allowed_response["result"]["isError"] is False
    assert engine.service.status(allowed).objective == "ALLOWED_STATE"


def test_emergency_failover_never_contacts_source_and_has_integrity_manifest(tmp_path: Path) -> None:
    root = tmp_path / "project"
    out = tmp_path / "failovers"
    root.mkdir()
    engine = _engine(tmp_path)
    engine.capture(root=root, kind="objective", value="CONTINUE_WITHOUT_SOURCE", source_provider="claude")
    engine.capture(root=root, kind="failure", value="CLAUDE_LIMIT_REACHED", source_provider="claude")

    bundle = prepare_emergency_failover(
        service=engine.service,
        root=root,
        source_provider="claude",
        target_provider="codex",
        output_root=out,
    )

    assert bundle.source_contacted is False
    payload = json.loads(bundle.json_path.read_text(encoding="utf-8"))
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    assert payload["source_status"] == "UNAVAILABLE"
    assert payload["source_contacted_during_failover"] is False
    assert payload["target_provider"] == "codex"
    assert payload["canonical_state"]["objective"] == "CONTINUE_WITHOUT_SOURCE"
    assert manifest["source_contacted"] is False
    assert set(manifest["files"]) == {"continuation.json", "continuation.md"}


def test_failover_for_project_a_contains_no_project_b_state(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    engine = _engine(tmp_path)
    engine.capture(root=a, kind="objective", value="SECRET_A_STATE", source_provider="claude")
    engine.capture(root=b, kind="objective", value="SECRET_B_STATE", source_provider="claude")

    bundle = prepare_emergency_failover(
        service=engine.service,
        root=a,
        source_provider="claude",
        target_provider="codex",
        output_root=tmp_path / "out",
    )
    combined = bundle.json_path.read_text(encoding="utf-8") + bundle.markdown_path.read_text(encoding="utf-8")
    assert "SECRET_A_STATE" in combined
    assert "SECRET_B_STATE" not in combined
