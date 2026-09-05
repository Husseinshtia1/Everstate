from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import Event, ProjectState
from .service import EverstateService


_ALLOWED_KINDS = {
    "objective",
    "task",
    "decision",
    "constraint",
    "failure",
    "blocker",
    "next_action",
}


@dataclass(frozen=True)
class CaptureResult:
    project_id: str
    state_version: int
    kind: str
    source_provider: str


def _clean(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("capture value must not be empty")
    if "\x00" in value:
        raise ValueError("capture value contains a NUL byte")
    if len(value) > 8000:
        raise ValueError("capture value exceeds the 8000-character structured-state limit")
    return value


class CaptureEngine:
    """Capture minimal structured project state without storing raw conversations.

    The source provider is provenance only. Canonical state is owned by Everstate and
    remains usable after that provider becomes unavailable.
    """

    def __init__(self, service: EverstateService):
        self.service = service

    def capture(
        self,
        *,
        root: Path,
        kind: str,
        value: str,
        source_provider: str,
        source_session: str | None = None,
    ) -> CaptureResult:
        root = root.expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"project root does not exist or is not a directory: {root}")
        kind = kind.strip().lower()
        if kind not in _ALLOWED_KINDS:
            raise ValueError(f"unsupported capture kind: {kind}")
        value = _clean(value)
        source_provider = source_provider.strip().lower()
        if not source_provider:
            raise ValueError("source_provider must not be empty")

        project_id = self.service.init_project(root)
        self.service.store.append_event(
            Event(
                project_id=project_id,
                event_type="provider_capture_received",
                source_type="provider_capture",
                source_locator=source_session,
                actor=source_provider,
                payload={"kind": kind, "value": value},
            )
        )

        state: ProjectState
        if kind == "objective":
            state = self.service.set_objective(root, value)
        elif kind == "task":
            state = self.service.set_task(root, value)
        elif kind == "decision":
            state = self.service.add_decision(root, value)
        elif kind == "constraint":
            state = self.service.add_constraint(root, value)
        elif kind == "failure":
            state = self.service.add_failure(root, value)
        elif kind == "blocker":
            state = self.service.add_blocker(root, value)
        else:
            state = self.service.set_next_action(root, value)

        return CaptureResult(
            project_id=project_id,
            state_version=state.version,
            kind=kind,
            source_provider=source_provider,
        )
