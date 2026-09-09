from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .continuity import ContinuationPacket
from .git_observer import snapshot_event
from .models import Event, ProjectState
from .storage import LocalStore


_IDENTITY_MARKER = Path(".everstate") / "project.json"


def stable_project_id(root: Path) -> str:
    digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"proj_{digest}"


def _identity_marker_path(root: Path) -> Path:
    return root / _IDENTITY_MARKER


def _read_identity_marker(root: Path) -> str | None:
    path = _identity_marker_path(root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    project_id = raw.get("project_id")
    if not isinstance(project_id, str):
        return None
    project_id = project_id.strip()
    if not project_id.startswith("proj_") or len(project_id) > 128:
        return None
    if not all(ch.isalnum() or ch in {"_", "-"} for ch in project_id):
        return None
    return project_id


def _write_identity_marker(root: Path, project_id: str) -> None:
    path = _identity_marker_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"version": 1, "project_id": project_id}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
    except OSError:
        return


class EverstateService:
    def __init__(self, store: LocalStore):
        self.store = store

    def _project_id_for_root(self, root: Path) -> str:
        marker_id = _read_identity_marker(root)
        if marker_id is None:
            return stable_project_id(root)
        existing = self.store.get_project(marker_id)
        if existing is None:
            return marker_id
        existing_root = Path(existing["root_path"])
        if existing_root.resolve() == root.resolve():
            return marker_id
        if not existing_root.exists():
            return marker_id
        return stable_project_id(root)

    @staticmethod
    def _carry_state(current: ProjectState | None, project_id: str, version: int) -> ProjectState:
        if current is None:
            return ProjectState(project_id=project_id, version=version)
        return ProjectState(
            project_id=project_id,
            version=version,
            objective=current.objective,
            current_task=current.current_task,
            active_constraints=list(current.active_constraints),
            decisions=list(current.decisions),
            failed_attempts=list(current.failed_attempts),
            blockers=list(current.blockers),
            modified_files=list(current.modified_files),
            next_action=current.next_action,
            unresolved_conflicts=list(current.unresolved_conflicts),
        )

    def init_project(self, root: Path) -> str:
        root = root.resolve()
        project_id = self._project_id_for_root(root)
        self.store.upsert_project(project_id, root.name, root)
        _write_identity_marker(root, project_id)

        try:
            event = snapshot_event(project_id, root)
        except RuntimeError:
            if self.store.latest_state(project_id) is None:
                event = Event(
                    project_id=project_id,
                    event_type="workspace_initialized",
                    source_type="local_workspace",
                    source_locator=str(root),
                    actor="local_runtime",
                    payload={"root": str(root), "git_backed": False},
                )
                self.store.append_event(event)
                self.store.mutate_state(
                    project_id,
                    lambda current, version: self._carry_state(current, project_id, version),
                )
            return project_id

        self.store.append_event(event)
        if self.store.latest_state(project_id) is None:
            self._materialize_git_state(project_id, event.payload)
        return project_id

    def _ensure_project(self, root: Path) -> tuple[Path, str]:
        root = root.resolve()
        project = self.store.get_project_by_root(root)
        if project is None:
            self.init_project(root)
            project = self.store.get_project_by_root(root)
            assert project is not None
        return root, project["id"]

    def refresh_project(self, root: Path) -> ProjectState:
        root, project_id = self._ensure_project(root)
        try:
            event = snapshot_event(project_id, root)
        except RuntimeError:
            latest = self.store.latest_state(project_id)
            if latest is not None:
                return latest
            return self.store.mutate_state(
                project_id,
                lambda current, version: self._carry_state(current, project_id, version),
            )

        recent_events = self.store.list_events(project_id, limit=200)
        latest_git_event = next((row for row in recent_events if row["event_type"] == "git_snapshot"), None)
        if latest_git_event is None or latest_git_event["content_hash"] != event.content_hash:
            self.store.append_event(event)
            return self._materialize_git_state(project_id, event.payload)
        latest = self.store.latest_state(project_id)
        if latest is None:
            return self._materialize_git_state(project_id, event.payload)
        return latest

    def _materialize_git_state(self, project_id: str, payload: dict) -> ProjectState:
        modified_files = list(payload.get("modified_files") or [])

        def mutation(previous: ProjectState | None, version: int) -> ProjectState:
            return ProjectState(
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

        return self.store.mutate_state(project_id, mutation)

    @staticmethod
    def _state_with_event(
        current: ProjectState | None,
        project_id: str,
        event_type: str,
        payload: dict,
        *,
        version: int,
    ) -> ProjectState:
        objective = current.objective if current else None
        current_task = current.current_task if current else None
        constraints = list(current.active_constraints) if current else []
        decisions = list(current.decisions) if current else []
        failures = list(current.failed_attempts) if current else []
        blockers = list(current.blockers) if current else []
        next_action = current.next_action if current else None
        value = str(payload.get("value", "")).strip()
        if event_type == "objective_set":
            objective = value
        elif event_type == "task_set":
            current_task = value
        elif event_type == "decision_added" and value and value not in decisions:
            decisions.append(value)
        elif event_type == "constraint_added" and value and value not in constraints:
            constraints.append(value)
        elif event_type == "failure_added" and value and value not in failures:
            failures.append(value)
        elif event_type == "blocker_added" and value and value not in blockers:
            blockers.append(value)
        elif event_type == "next_action_set":
            next_action = value
        elif event_type not in {
            "objective_set", "task_set", "decision_added", "constraint_added",
            "failure_added", "blocker_added", "next_action_set",
        }:
            raise ValueError(f"Unsupported state event: {event_type}")
        return ProjectState(
            project_id=project_id,
            version=version,
            objective=objective,
            current_task=current_task,
            active_constraints=constraints,
            decisions=decisions,
            failed_attempts=failures,
            blockers=blockers,
            modified_files=list(current.modified_files) if current else [],
            next_action=next_action,
            unresolved_conflicts=list(current.unresolved_conflicts) if current else [],
        )

    def _record_state_event(self, root: Path, event_type: str, payload: dict) -> ProjectState:
        root, project_id = self._ensure_project(root)
        event = Event(
            project_id=project_id,
            event_type=event_type,
            source_type="explicit_user_input",
            source_locator=str(root),
            actor="user",
            payload=payload,
        )
        self.store.append_event(event)
        return self.store.mutate_state(
            project_id,
            lambda current, version: self._state_with_event(
                current, project_id, event_type, payload, version=version,
            ),
        )

    def set_objective(self, root: Path, value: str) -> ProjectState:
        return self._record_state_event(root, "objective_set", {"value": value})

    def set_task(self, root: Path, value: str) -> ProjectState:
        return self._record_state_event(root, "task_set", {"value": value})

    def add_decision(self, root: Path, value: str) -> ProjectState:
        return self._record_state_event(root, "decision_added", {"value": value})

    def add_constraint(self, root: Path, value: str) -> ProjectState:
        return self._record_state_event(root, "constraint_added", {"value": value})

    def add_failure(self, root: Path, value: str) -> ProjectState:
        return self._record_state_event(root, "failure_added", {"value": value})

    def add_blocker(self, root: Path, value: str) -> ProjectState:
        return self._record_state_event(root, "blocker_added", {"value": value})

    def set_next_action(self, root: Path, value: str) -> ProjectState:
        return self._record_state_event(root, "next_action_set", {"value": value})

    def status(self, root: Path) -> ProjectState:
        return self.refresh_project(root)

    def continuation_packet(self, root: Path) -> ContinuationPacket:
        return ContinuationPacket.from_state(self.refresh_project(root))

    def continuation_text(self, root: Path) -> str:
        return self.continuation_packet(root).to_prompt()

    @staticmethod
    def _append_section(lines: list[str], title: str, items: list[str], empty: str) -> None:
        lines.extend(["", title])
        if items:
            lines.extend(f"- {item}" for item in items)
        else:
            lines.append(f"- {empty}")

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
            lines.append("- Working tree clean or file tracking unavailable")
        self._append_section(lines, "Active decisions:", state.decisions, "None captured yet")
        self._append_section(lines, "Active constraints:", state.active_constraints, "None captured yet")
        self._append_section(lines, "Known failed attempts:", state.failed_attempts, "None captured yet")
        self._append_section(lines, "Blockers:", state.blockers, "None captured yet")
        self._append_section(lines, "Unresolved conflicts:", state.unresolved_conflicts, "None detected")
        lines.extend(["", f"Next action: {state.next_action or 'Not yet established'}"])
        return "\n".join(lines)
