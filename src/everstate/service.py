from __future__ import annotations

import hashlib
from pathlib import Path

from .git_observer import snapshot_event
from .models import ProjectState
from .storage import LocalStore


def stable_project_id(root: Path) -> str:
    digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"proj_{digest}"


class EverstateService:
    def __init__(self, store: LocalStore):
        self.store = store

    def init_project(self, root: Path) -> str:
        root = root.resolve()
        project_id = stable_project_id(root)
        self.store.upsert_project(project_id, root.name, root)
        event = snapshot_event(project_id, root)
        self.store.append_event(event)
        self._materialize_git_state(project_id, event.payload)
        return project_id

    def refresh_project(self, root: Path) -> ProjectState:
        root = root.resolve()
        project = self.store.get_project_by_root(root)
        if project is None:
            self.init_project(root)
            project = self.store.get_project_by_root(root)
            assert project is not None
        project_id = project["id"]
        event = snapshot_event(project_id, root)
        existing_events = self.store.list_events(project_id, limit=1)
        if not existing_events or existing_events[0]["content_hash"] != event.content_hash:
            self.store.append_event(event)
            return self._materialize_git_state(project_id, event.payload)
        latest = self.store.latest_state(project_id)
        if latest is None:
            return self._materialize_git_state(project_id, event.payload)
        return latest

    def _materialize_git_state(self, project_id: str, payload: dict) -> ProjectState:
        previous = self.store.latest_state(project_id)
        version = 1 if previous is None else previous.version + 1
        modified_files = list(payload.get("modified_files") or [])
        state = ProjectState(
            project_id=project_id,
            version=version,
            objective=previous.objective if previous else None,
            current_task=previous.current_task if previous else None,
            active_constraints=list(previous.active_constraints) if previous else [],
            decisions=list(previous.decisions) if previous else [],
            failed_attempts=list(previous.failed_attempts) if previous else [],
            blockers=list(previous.blockers) if previous else [],
            modified_files=modified_files,
            next_action=previous.next_action if previous else None,
            unresolved_conflicts=list(previous.unresolved_conflicts) if previous else [],
        )
        self.store.save_state(state)
        return state

    def status(self, root: Path) -> ProjectState:
        return self.refresh_project(root)

    def resume_text(self, root: Path) -> str:
        state = self.refresh_project(root)
        lines = [
            "EVERSTATE PROJECT RESUME",
            f"State version: {state.version}",
            "",
            f"Objective: {state.objective or 'Not yet established'}",
            f"Current task: {state.current_task or 'Not yet established'}",
            "",
            "Modified files:",
        ]
        if state.modified_files:
            lines.extend(f"- {path}" for path in state.modified_files)
        else:
            lines.append("- Working tree clean")

        lines.extend(["", "Active constraints:"])
        lines.extend(f"- {item}" for item in state.active_constraints) or lines.append("- None captured yet")

        lines.extend(["", "Known failed attempts:"])
        lines.extend(f"- {item}" for item in state.failed_attempts) or lines.append("- None captured yet")

        lines.extend(["", "Blockers:"])
        lines.extend(f"- {item}" for item in state.blockers) or lines.append("- None captured yet")

        lines.extend(["", f"Next action: {state.next_action or 'Not yet established'}"])
        return "\n".join(lines)
