from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


PROJECTS_FALLBACK_URL = "claude://claude.ai/project/invalid"


@dataclass(frozen=True)
class ClaudeDesktopAuthorizedProbe:
    profile_exists: bool
    scheme_handler: str | None
    opener: str | None
    desktop_process_detected: bool
    can_attempt_ui_navigation: bool
    navigation_attempted: bool = False
    navigation_exit_code: int | None = None


def _profile_exists(home: Path | None = None) -> bool:
    home = (home or Path.home()).expanduser()
    return (home / ".config" / "Claude").is_dir() or (
        home / "Library" / "Application Support" / "Claude"
    ).is_dir()


def _query_scheme_handler() -> str | None:
    xdg_mime = shutil.which("xdg-mime")
    if not xdg_mime:
        return None
    try:
        result = subprocess.run(
            [xdg_mime, "query", "default", "x-scheme-handler/claude"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value or None


def _desktop_process_detected() -> bool:
    pgrep = shutil.which("pgrep")
    if not pgrep:
        return False
    try:
        result = subprocess.run(
            [pgrep, "-af", "Claude|claude-desktop"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def _opener() -> str | None:
    return shutil.which("xdg-open") or shutil.which("gio")


def probe_claude_desktop_authorized(*, open_projects: bool = False) -> ClaudeDesktopAuthorizedProbe:
    opener = _opener()
    handler = _query_scheme_handler()
    can_attempt = bool(opener and handler)
    attempted = False
    exit_code: int | None = None

    if open_projects and can_attempt:
        attempted = True
        command = [opener, PROJECTS_FALLBACK_URL]
        if Path(opener).name == "gio":
            command = [opener, "open", PROJECTS_FALLBACK_URL]
        try:
            result = subprocess.run(command, timeout=10, check=False)
            exit_code = result.returncode
        except (OSError, subprocess.TimeoutExpired):
            exit_code = -1

    return ClaudeDesktopAuthorizedProbe(
        profile_exists=_profile_exists(),
        scheme_handler=handler,
        opener=opener,
        desktop_process_detected=_desktop_process_detected(),
        can_attempt_ui_navigation=can_attempt,
        navigation_attempted=attempted,
        navigation_exit_code=exit_code,
    )
