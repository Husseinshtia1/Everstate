from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .capture import CaptureEngine
from .service import EverstateService
from .storage import LocalStore


SERVER_NAME = "everstate-capture"
SERVER_VERSION = "0.1.0"
LATEST_PROTOCOL = "2026-07-28"
LEGACY_PROTOCOL = "2025-11-25"


def _runtime_home() -> Path:
    configured = os.environ.get("EVERSTATE_HOME", "").strip()
    return Path(configured).expanduser().resolve() if configured else Path.home().resolve()


def _engine() -> CaptureEngine:
    store = LocalStore(_runtime_home() / ".everstate" / "everstate.db")
    return CaptureEngine(EverstateService(store))


def _authorized_root(root: Path) -> Path:
    """Resolve and enforce the optional extension-scoped project boundary.

    EVERSTATE_ALLOWED_ROOT is deliberately exact-match, not parent/child containment.
    A Claude Desktop extension configured for one project cannot mutate another
    project even if a tool call supplies a different path.
    """
    resolved = root.expanduser().resolve()
    allowed_raw = os.environ.get("EVERSTATE_ALLOWED_ROOT", "").strip()
    if not allowed_raw:
        return resolved
    allowed = Path(allowed_raw).expanduser().resolve()
    if resolved != allowed:
        raise ValueError(
            f"project root is outside the configured Everstate MCP boundary: {resolved} != {allowed}"
        )
    return resolved


def _request_protocol(message: dict[str, Any]) -> str | None:
    params = message.get("params") or {}
    meta = params.get("_meta") or {}
    return meta.get("io.modelcontextprotocol/protocolVersion")


def _is_modern(message: dict[str, Any]) -> bool:
    return _request_protocol(message) == LATEST_PROTOCOL or message.get("method") == "server/discover"


def _server_meta() -> dict[str, Any]:
    return {
        "io.modelcontextprotocol/serverInfo": {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
        }
    }


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


def _tool_catalog() -> list[dict[str, Any]]:
    return [
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
    ]


def _tools_list(*, modern: bool) -> dict[str, Any]:
    result: dict[str, Any] = {"tools": _tool_catalog()}
    if modern:
        result.update(
            {
                "resultType": "complete",
                "ttlMs": 60000,
                "cacheScope": "private",
                "_meta": _server_meta(),
            }
        )
    return result


def _result_text(payload: Any, *, is_error: bool = False, modern: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, sort_keys=True)}],
        "isError": is_error,
    }
    if modern:
        result["resultType"] = "complete"
        result["_meta"] = _server_meta()
    return result


def handle_request(message: dict[str, Any], engine: CaptureEngine | None = None) -> dict[str, Any] | None:
    if message.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32600, "message": "Invalid Request"}}

    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        # Legacy notifications/initialized is intentionally accepted without output.
        return None

    if method == "server/discover":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "resultType": "complete",
                "supportedVersions": [LATEST_PROTOCOL, LEGACY_PROTOCOL],
                "capabilities": {"tools": {}},
                "_meta": _server_meta(),
                "instructions": (
                    "Everstate captures minimal structured project state locally for source-independent continuation."
                ),
                "ttlMs": 60000,
                "cacheScope": "private",
            },
        }

    if method == "initialize":
        requested = ((message.get("params") or {}).get("protocolVersion") or LEGACY_PROTOCOL)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": requested,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    modern = _is_modern(message)

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": _tools_list(modern=modern)}

    if method != "tools/call":
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}

    params = message.get("params") or {}
    name = params.get("name")
    arguments = params.get("arguments") or {}
    engine = engine or _engine()

    try:
        if name == "everstate_capture":
            root = _authorized_root(Path(str(arguments["project_root"])))
            result = engine.capture(
                root=root,
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
            root = _authorized_root(Path(str(arguments["project_root"])))
            if not root.is_dir():
                raise ValueError(f"project root does not exist or is not a directory: {root}")
            state = engine.service.status(root)
            payload = state.model_dump(mode="json")
        else:
            raise ValueError(f"unknown tool: {name}")
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": _result_text({"ok": False, "error": str(exc)}, is_error=True, modern=modern),
        }

    return {"jsonrpc": "2.0", "id": request_id, "result": _result_text(payload, modern=modern)}


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
