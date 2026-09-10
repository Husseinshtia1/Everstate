from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import Event


@dataclass(slots=True)
class GitSnapshot:
    branch: str
    head: str | None
    status_porcelain: str
    diff_stat: str
    modified_files: list[str]


def _run_git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git command failed")
    # Do not use .strip(): porcelain status intentionally uses a leading space
    # as one of its two status columns (for example " M file.txt"). Removing
    # that byte shifts the path and silently drops its first character.
    return proc.stdout.rstrip("\r\n")


def ensure_git_repo(root: Path) -> None:
    value = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if value != "true":
        raise RuntimeError(f"{root} is not a Git repository")


def _normalized_status_path(line: str) -> str | None:
    if len(line) < 4:
        return None
    path = line[3:]
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    return path


def _is_generated_or_internal(path: str) -> bool:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return False

    # Runtime/control-plane artifacts are evidence about orchestration, not
    # product source changes. They must never enter canonical modified_files or
    # alter the Git snapshot identity merely because Everstate/Ruflo ran.
    if parts[0] in {".everstate", ".claude-flow"}:
        return True
    if "__pycache__" in parts:
        return True
    if normalized.endswith((".pyc", ".pyo")):
        return True
    return False


def snapshot(root: Path) -> GitSnapshot:
    root = root.resolve()
    ensure_git_repo(root)

    branch = _run_git(root, "branch", "--show-current", check=False) or "DETACHED"
    head = _run_git(root, "rev-parse", "HEAD", check=False) or None
    # Git quotes non-ASCII paths by default according to core.quotePath. The
    # canonical state needs the actual repository path, not a C-style escaped
    # representation, so disable quoting for this machine-readable snapshot.
    raw_status = _run_git(
        root,
        "-c",
        "core.quotepath=false",
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    diff_stat = _run_git(root, "-c", "core.quotepath=false", "diff", "--stat", "HEAD", check=False)

    filtered_status_lines: list[str] = []
    modified_files: list[str] = []
    for line in raw_status.splitlines():
        path = _normalized_status_path(line)
        if path is None or _is_generated_or_internal(path):
            continue
        filtered_status_lines.append(line)
        modified_files.append(path)

    status = "\n".join(filtered_status_lines)
    return GitSnapshot(
        branch=branch,
        head=head,
        status_porcelain=status,
        diff_stat=diff_stat,
        modified_files=sorted(set(modified_files)),
    )


def snapshot_event(project_id: str, root: Path) -> Event:
    snap = snapshot(root)
    canonical = "\n".join([snap.branch, snap.head or "", snap.status_porcelain, snap.diff_stat])
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return Event(
        project_id=project_id,
        event_type="git_snapshot",
        source_type="git",
        source_locator=str(root.resolve()),
        actor="local_runtime",
        content_hash=digest,
        payload={
            "branch": snap.branch,
            "head": snap.head,
            "status": snap.status_porcelain,
            "diff_stat": snap.diff_stat,
            "modified_files": snap.modified_files,
        },
    )
