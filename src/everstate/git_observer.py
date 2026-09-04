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
    return proc.stdout.strip()


def ensure_git_repo(root: Path) -> None:
    value = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if value != "true":
        raise RuntimeError(f"{root} is not a Git repository")


def snapshot(root: Path) -> GitSnapshot:
    root = root.resolve()
    ensure_git_repo(root)

    branch = _run_git(root, "branch", "--show-current", check=False) or "DETACHED"
    head = _run_git(root, "rev-parse", "HEAD", check=False) or None
    status = _run_git(root, "status", "--porcelain=v1", "--untracked-files=all")
    diff_stat = _run_git(root, "diff", "--stat", "HEAD", check=False)

    modified_files: list[str] = []
    for line in status.splitlines():
        if len(line) >= 4:
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            modified_files.append(path)

    return GitSnapshot(
        branch=branch,
        head=head,
        status_porcelain=status,
        diff_stat=diff_stat,
        modified_files=sorted(set(modified_files)),
    )


def snapshot_event(project_id: str, root: Path) -> Event:
    snap = snapshot(root)
    canonical = "\n".join(
        [
            snap.branch,
            snap.head or "",
            snap.status_porcelain,
            snap.diff_stat,
        ]
    )
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
