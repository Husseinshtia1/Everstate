from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .service import EverstateService


@dataclass(frozen=True)
class WorkStartCheckpoint:
    project_id: str
    state_version: int
    task: str
    next_action: str
    target: str


def _clean(label: str, value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label} must not be empty")
    if "\x00" in value:
        raise ValueError(f"{label} contains a NUL byte")
    return value


def checkpoint_before_provider(
    service: EverstateService,
    *,
    root: Path,
    task: str,
    target: str,
    objective: str | None = None,
    next_action: str | None = None,
) -> WorkStartCheckpoint:
    """Persist user-owned semantic state before any provider is launched.

    This function has no provider adapter parameter by design. A caller must finish
    this checkpoint successfully before it is allowed to contact or launch an AI.
    """
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project root does not exist or is not a directory: {root}")

    task = _clean("task", task)
    target = _clean("target", target).lower()
    if objective is not None:
        objective = _clean("objective", objective)
        service.set_objective(root, objective)

    service.set_task(root, task)
    resolved_next = _clean(
        "next_action",
        next_action if next_action is not None else f"Continue current task in {target}: {task}",
    )
    state = service.set_next_action(root, resolved_next)

    return WorkStartCheckpoint(
        project_id=state.project_id,
        state_version=state.version,
        task=task,
        next_action=resolved_next,
        target=target,
    )
