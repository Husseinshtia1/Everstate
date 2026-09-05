from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .capture import CaptureEngine
from .service import EverstateService
from .storage import LocalStore


SERVER_NAME = "everstate-capture"
SERVER_VERSION = "0.1.0"
LATEST_PROTOCOL = "2026-07-28"


def _engine() -> CaptureEngine:
    store = LocalStore(Path.home() / ".everstate" / "everstate.db")
    return CaptureEngine(EverstateService(store))


def _tool_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "description": "Absolute or user-relative project directory."},
            "kind": {
                "type": "string",
                "enum": ["objective", "task", "decision", "constraint", "failure", "blocker", "next_action"],
            },
            "value": {"type": "string", "maxLength": 8000},
            "source_provider": {"type": "string"},
            "source_session": {"type": ["string", "null"]},
        },
        "required": ["project_root", "kind", "value", "source_provider"],
        "additionalProperties": False,
    }


def _tools_list() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": "everstate_capture",
                "description": (
                    "Persist one minimal structured project-state fact in Everstate. "
                    "Use during work so continuation does not depend on the current AI remaining available. "
                    "Do not send raw full conversation transcripts or secrets."
                ),
                "inputSchema": _tool_schema(),
            },
            {
                "name": "everstate_status",
                "description": "Read the canonical Everstate state for one explicitly selected project directory.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"project_root": {"type": "string"}},
                    "required": ["project_root"],
                    "additionalProperties": False,
                },
            },
        ],
        "ttlMs": 60000,
        "cacheScope": "server",
    }


def _result_text(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, sort_keys=True)}],
        "isError": is_error,
    }


def handle_request(message: dict[str, Any], engine: CaptureEngine | None = None) -> dict[str, Any] | None:
    if message.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32600, "message": "Invalid Request"}}

    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        # Notifications are deliberately side-effect free in this server.
        return None

    if method == "initialize":
        requested = ((message.get("params") or {}).get("protocolVersion") or LATEST_PROTOCOL)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": requested,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method == "server/discover":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": LATEST_PROTOCOL,
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "capabilities": {"tools": True},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": _tools_list()}

    if method != "tools/call":
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}

    params = message.get("params") or {}
    name = params.get("name")
    arguments = params.get("arguments") or {}
    engine = engine or _engine()

    try:
        if name == "everstate_capture":
            result = engine.capture(
                root=Path(str(arguments["project_root"])),
                kind=str(arguments["kind"]),
                value=str(arguments["value"]),
                source_provider=str(arguments["source_provider"]),
                source_session=(str(arguments["source_session"]) if arguments.get("source_session") is not None else None),
            )
            payload = {
                "ok": True,
                "project_id": result.project_id,
                "state_version": result.state_version,
                "kind": result.kind,
                "source_provider": result.source_provider,
            }
        elif name == "everstate_status":
            root = Path(str(arguments["project_root"])).expanduser().resolve()
            if not root.is_dir():
                raise ValueError(f"project root does not exist or is not a directory: {root}")
            state = engine.service.status(root)
            payload = state.model_dump(mode="json")
        else:
            raise ValueError(f"unknown tool: {name}")
    except (KeyError, TypeError, ValueError) as exc:
        return {"jsonrpc": "2.0", "id": request_id, "result": _result_text({"ok": False, "error": str(exc)}, is_error=True)}

    return {"jsonrpc": "2.0", "id": request_id, "result": _result_text(payload)}


def main() -> None:
    """Run a local stdio MCP server. One JSON-RPC object per input line."""
    engine = _engine()
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
            response = handle_request(message, engine)
        except json.JSONDecodeError:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
