from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extensions" / "claude-desktop"


def test_manifest_has_required_mcpb_v03_fields_and_exact_tools() -> None:
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "0.3"
    assert manifest["name"] == "everstate-capture"
    assert manifest["server"]["type"] == "node"
    assert manifest["server"]["entry_point"] == "server/proxy.js"
    assert manifest["server"]["mcp_config"]["command"] == "node"
    assert manifest["server"]["mcp_config"]["env"]["EVERSTATE_ALLOWED_ROOT"] == "${user_config.project_root}"
    assert manifest["server"]["mcp_config"]["env"]["EVERSTATE_MCP_COMMAND"] == "${user_config.everstate_mcp_command}"
    assert {tool["name"] for tool in manifest["tools"]} == {"everstate_capture", "everstate_status"}
    assert manifest["user_config"]["project_root"]["type"] == "directory"
    assert manifest["user_config"]["project_root"]["required"] is True
    assert manifest["user_config"]["everstate_mcp_command"]["type"] == "file"
    assert manifest["user_config"]["everstate_mcp_command"]["required"] is True


def test_proxy_is_fail_closed_and_never_invokes_a_shell() -> None:
    proxy = (EXTENSION / "server" / "proxy.js").read_text(encoding="utf-8")
    assert 'shell: false' in proxy
    assert 'EVERSTATE_MCP_COMMAND' in proxy
    assert 'EVERSTATE_ALLOWED_ROOT' in proxy
    assert 'path.isAbsolute(command)' in proxy
    assert 'path.isAbsolute(allowedRoot)' in proxy
    assert 'spawn(command, []' in proxy
    assert 'exec(' not in proxy
    assert 'execSync(' not in proxy
