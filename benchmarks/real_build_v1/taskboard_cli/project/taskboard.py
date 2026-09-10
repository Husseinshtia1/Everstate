from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def storage_path() -> Path:
    return Path(os.environ.get("TASKBOARD_FILE", ".taskboard.json"))


def load_tasks() -> list[dict[str, object]]:
    path = storage_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_tasks(tasks: list[dict[str, object]]) -> None:
    # TODO: implement safe persistence without external dependencies.
    raise NotImplementedError


def add_task(title: str) -> int:
    # TODO: validate title, allocate a stable sequential id, persist, return id.
    raise NotImplementedError


def mark_done(task_id: int) -> bool:
    # TODO: mark an existing task done and persist it; return False if missing.
    raise NotImplementedError


def render_tasks() -> str:
    # TODO: render one deterministic line per task.
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    # TODO: implement commands: add TITLE, list, done ID.
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
