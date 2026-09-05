from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


PROJECTS_FALLBACK_URL = "claude://claude.ai/project/invalid"
PROJECT_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass(frozen=True)
class ClaudeDesktopAuthorizedProbe:
    profile_exists: bool
    scheme_handler: str | None
    opener: str | None
    desktop_process_detected: bool
    can_attempt_ui_navigation: bool
    navigation_attempted: bool = False
    navigation_exit_code: int | None = None


@dataclass(frozen=True)
class ClaudeExactProjectOpenResult:
    project_id: str
    valid_project_id: bool
    scheme_handler: str | None
    opener: str | None
    attempted: bool
    exit_code: int | None

    @property
    def os_handoff_succeeded(self) -> bool:
        return self.attempted and self.exit_code == 0


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


def _open_url(opener: str, url: str) -> int:
    command = [opener, url]
    if Path(opener).name == "gio":
        command = [opener, "open", url]
    try:
        result = subprocess.run(command, timeout=10, check=False)
        return result.returncode
    except (OSError, subprocess.TimeoutExpired):
        return -1


def probe_claude_desktop_authorized(*, open_projects: bool = False) -> ClaudeDesktopAuthorizedProbe:
    opener = _opener()
    handler = _query_scheme_handler()
    can_attempt = bool(opener and handler)
    attempted = False
    exit_code: int | None = None

    if open_projects and can_attempt:
        attempted = True
        exit_code = _open_url(opener, PROJECTS_FALLBACK_URL)

    return ClaudeDesktopAuthorizedProbe(
        profile_exists=_profile_exists(),
        scheme_handler=handler,
        opener=opener,
        desktop_process_detected=_desktop_process_detected(),
        can_attempt_ui_navigation=can_attempt,
        navigation_attempted=attempted,
        navigation_exit_code=exit_code,
    )


def open_claude_exact_project(project_id: str) -> ClaudeExactProjectOpenResult:
    project_id = project_id.strip()
    valid = bool(PROJECT_ID_RE.fullmatch(project_id))
    opener = _opener()
    handler = _query_scheme_handler()
    can_attempt = bool(valid and opener and handler)
    exit_code: int | None = None
    if can_attempt:
        exit_code = _open_url(opener, f"claude://claude.ai/project/{project_id}")
    return ClaudeExactProjectOpenResult(
        project_id=project_id,
        valid_project_id=valid,
        scheme_handler=handler,
        opener=opener,
        attempted=can_attempt,
        exit_code=exit_code,
    )
