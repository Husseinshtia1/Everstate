from __future__ import annotations

import json
from pathlib import Path

from everstate.capture import CaptureEngine
from everstate.emergency_failover import prepare_emergency_failover
from everstate.mcp_server import handle_request
from everstate.service import EverstateService
from everstate.storage import LocalStore


def _engine(tmp_path: Path) -> CaptureEngine:
    return CaptureEngine(EverstateService(LocalStore(tmp_path / "everstate.db")))


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
