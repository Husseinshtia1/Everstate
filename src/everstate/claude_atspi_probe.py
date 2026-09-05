from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ClaudeAtspiProbe:
    gdbus_available: bool
    busctl_available: bool
    accessibility_bus_available: bool
    accessibility_enabled: bool | None
    accessibility_bus_address_available: bool
    registry_available: bool
    claude_registered: bool
    safe_for_tree_probe: bool


def _run(command: list[str], timeout: int = 5) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _parse_gvariant_bool(text: str) -> bool | None:
    lowered = text.lower()
    if "true" in lowered:
        return True
    if "false" in lowered:
        return False
    return None


def _get_accessibility_bus_address(gdbus: str) -> str | None:
    result = _run(
        [
            gdbus,
            "call",
            "--session",
            "--dest",
            "org.a11y.Bus",
            "--object-path",
            "/org/a11y/bus",
            "--method",
            "org.a11y.Bus.GetAddress",
        ]
    )
    if not result or result.returncode != 0:
        return None
    match = re.search(r"['\"](unix:[^'\"]+)['\"]", result.stdout)
    return match.group(1) if match else None


def probe_claude_atspi() -> ClaudeAtspiProbe:
    gdbus = shutil.which("gdbus")
    busctl = shutil.which("busctl")

    if not gdbus:
        return ClaudeAtspiProbe(False, bool(busctl), False, None, False, False, False, False)

    status = _run(
        [
            gdbus,
            "call",
            "--session",
            "--dest",
            "org.a11y.Bus",
            "--object-path",
            "/org/a11y/bus",
            "--method",
            "org.freedesktop.DBus.Properties.Get",
            "org.a11y.Status",
            "IsEnabled",
        ]
    )
    accessibility_bus_available = bool(status and status.returncode == 0)
    accessibility_enabled = _parse_gvariant_bool(status.stdout) if accessibility_bus_available else None

    address = _get_accessibility_bus_address(gdbus) if accessibility_bus_available else None
    registry_available = False
    claude_registered = False

    if address and busctl:
        listed = _run([busctl, f"--address={address}", "list"])
        if listed and listed.returncode == 0:
            registry_available = "org.a11y.atspi.Registry" in listed.stdout
            # AT-SPI clients often have unique bus names, so process labels may or may
            # not contain Claude. Treat this only as a positive signal, never as proof
            # of absence when not found.
            claude_registered = bool(re.search(r"claude", listed.stdout, re.IGNORECASE))

    safe_for_tree_probe = bool(
        accessibility_bus_available
        and accessibility_enabled is True
        and address
        and registry_available
    )

    return ClaudeAtspiProbe(
        gdbus_available=True,
        busctl_available=bool(busctl),
        accessibility_bus_available=accessibility_bus_available,
        accessibility_enabled=accessibility_enabled,
        accessibility_bus_address_available=bool(address),
        registry_available=registry_available,
        claude_registered=claude_registered,
        safe_for_tree_probe=safe_for_tree_probe,
    )
