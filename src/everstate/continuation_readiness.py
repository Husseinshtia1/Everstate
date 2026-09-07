from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import ProjectState
from .service import EverstateService


_REQUIRED_FIELDS = ("objective", "current_task", "next_action")
_SEMANTIC_EVENT_TYPES = {
    "provider_capture_received",
    "objective_set",
    "task_set",
    "decision_added",
    "constraint_added",
    "failure_added",
    "blocker_added",
    "next_action_set",
}


@dataclass(frozen=True)
class ContinuationReadiness:
    status: str
    project_id: str
    state_version: int
    missing_fields: tuple[str, ...]
    provider_capture_count: int
    last_provider_capture_at: str | None
    semantic_capture_count: int
    last_semantic_capture_at: str | None
    semantic_zero_loss_proven: bool = False

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "project_id": self.project_id,
            "state_version": self.state_version,
            "missing_fields": list(self.missing_fields),
            "provider_capture_count": self.provider_capture_count,
            "last_provider_capture_at": self.last_provider_capture_at,
            "semantic_capture_count": self.semantic_capture_count,
            "last_semantic_capture_at": self.last_semantic_capture_at,
            "semantic_zero_loss_proven": self.semantic_zero_loss_proven,
        }


def assess_continuation_readiness(
    service: EverstateService,
    root: Path,
    *,
    state: ProjectState | None = None,
) -> ContinuationReadiness:
    """Report whether canonical state has the minimum fields for handoff.

    READY requires objective, current task, next action, and semantic provenance.
    Provenance may come from an AI/provider capture or from explicit user-owned
    Everstate state events. Explicit user checkpoints are at least as authoritative
    as model-invoked MCP capture and are the preferred pre-provider path.

    READY still does not claim zero-loss semantic capture. State created only
    inside a provider after the last checkpoint may be lost if that provider
    becomes unavailable before another capture occurs.
    """
    root = root.expanduser().resolve()
    state = state or service.status(root)
    rows = service.store.list_events(state.project_id, limit=1000)

    provider_rows = [row for row in rows if row["event_type"] == "provider_capture_received"]
    semantic_rows = [row for row in rows if row["event_type"] in _SEMANTIC_EVENT_TYPES]

    last_provider_capture_at = provider_rows[0]["timestamp"] if provider_rows else None
    last_semantic_capture_at = semantic_rows[0]["timestamp"] if semantic_rows else None

    missing = [field for field in _REQUIRED_FIELDS if not getattr(state, field)]
    if not semantic_rows:
        missing.append("semantic_capture_provenance")

    return ContinuationReadiness(
        status="READY" if not missing else "PARTIAL",
        project_id=state.project_id,
        state_version=state.version,
        missing_fields=tuple(missing),
        provider_capture_count=len(provider_rows),
        last_provider_capture_at=last_provider_capture_at,
        semantic_capture_count=len(semantic_rows),
        last_semantic_capture_at=last_semantic_capture_at,
        semantic_zero_loss_proven=False,
    )
