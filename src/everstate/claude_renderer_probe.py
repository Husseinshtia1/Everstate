from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen


_PORT_RE = re.compile(r"--remote-debugging-port(?:=|\s+)(\d{1,5})")
_ADDR_RE = re.compile(r"--remote-debugging-address(?:=|\s+)([^\s]+)")


@dataclass(frozen=True)
class ClaudeRendererReadiness:
    claude_processes: int
    remote_debugging_enabled: bool
    port: int | None
    address: str | None
    loopback_only: bool
    json_endpoint_reachable: bool
    target_count: int

    @property
    def safe_for_readonly_probe(self) -> bool:
        return (
            self.remote_debugging_enabled
            and self.port is not None
            and self.loopback_only
            and self.json_endpoint_reachable
        )


def _read_cmdline(path: Path) -> str:
    try:
        return path.read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def probe_claude_renderer(proc_root: Path = Path("/proc")) -> ClaudeRendererReadiness:
    claude_cmdlines: list[str] = []
    for entry in proc_root.iterdir() if proc_root.exists() else []:
        if not entry.name.isdigit():
            continue
        cmdline = _read_cmdline(entry / "cmdline")
        lower = cmdline.lower()
        if "claude" in lower and ("electron" in lower or "claude" in lower):
            claude_cmdlines.append(cmdline)

    port: int | None = None
    address: str | None = None
    for cmdline in claude_cmdlines:
        match = _PORT_RE.search(cmdline)
        if match:
            candidate = int(match.group(1))
            if 1 <= candidate <= 65535:
                port = candidate
                addr_match = _ADDR_RE.search(cmdline)
                address = addr_match.group(1) if addr_match else None
                break

    enabled = port is not None
    # Chromium/Electron remote debugging is expected to bind locally by default in
    # common setups, but Everstate requires explicit loopback evidence before it
    # treats the channel as safe enough for further automation.
    loopback = address in {"127.0.0.1", "localhost", "::1"}
    reachable = False
    target_count = 0

    if enabled and loopback and port is not None:
        try:
            with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1.5) as response:
                if response.status == 200:
                    import json

                    payload = json.loads(response.read().decode("utf-8", "replace"))
                    if isinstance(payload, list):
                        reachable = True
                        target_count = len(payload)
        except Exception:
            reachable = False

    return ClaudeRendererReadiness(
        claude_processes=len(claude_cmdlines),
        remote_debugging_enabled=enabled,
        port=port,
        address=address,
        loopback_only=loopback,
        json_endpoint_reachable=reachable,
        target_count=target_count,
    )
