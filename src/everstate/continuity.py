from __future__ import annotations

from pydantic import BaseModel, Field

from .models import ProjectState


class ContinuationPacket(BaseModel):
    project_id: str
    state_version: int
    objective: str | None = None
    current_task: str | None = None
    decisions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    failed_attempts: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    modified_files: list[str] = Field(default_factory=list)
    unresolved_conflicts: list[str] = Field(default_factory=list)
    next_action: str | None = None

    @classmethod
    def from_state(cls, state: ProjectState) -> "ContinuationPacket":
        return cls(
            project_id=state.project_id,
            state_version=state.version,
            objective=state.objective,
            current_task=state.current_task,
            decisions=list(state.decisions),
            constraints=list(state.active_constraints),
            failed_attempts=list(state.failed_attempts),
            blockers=list(state.blockers),
            modified_files=list(state.modified_files),
            unresolved_conflicts=list(state.unresolved_conflicts),
            next_action=state.next_action,
        )

    def to_prompt(self) -> str:
        lines = [
            "EVERSTATE CONTINUATION PACKET",
            f"PROJECT ID: {self.project_id}",
            f"STATE VERSION: {self.state_version}",
            "",
            "CONTINUATION CONTRACT",
            "You are continuing an existing task. Treat CURRENT state as authoritative unless you observe newer local evidence.",
            "Do not repeat FAILED ATTEMPTS unless relevant conditions have changed.",
            "Preserve ACTIVE CONSTRAINTS. Surface conflicts instead of silently guessing.",
            "",
            f"OBJECTIVE: {self.objective or 'Not established'}",
            f"CURRENT TASK: {self.current_task or 'Not established'}",
        ]
        self._section(lines, "ACTIVE DECISIONS", self.decisions, "None captured")
        self._section(lines, "ACTIVE CONSTRAINTS", self.constraints, "None captured")
        self._section(lines, "FAILED ATTEMPTS", self.failed_attempts, "None captured")
        self._section(lines, "BLOCKERS", self.blockers, "None captured")
        self._section(lines, "MODIFIED FILES", self.modified_files, "Working tree clean")
        self._section(lines, "UNRESOLVED CONFLICTS", self.unresolved_conflicts, "None detected")
        lines.extend(["", f"NEXT ACTION: {self.next_action or 'Not established'}"])
        return "\n".join(lines)

    @staticmethod
    def _section(lines: list[str], title: str, values: list[str], empty: str) -> None:
        lines.extend(["", title])
        if values:
            lines.extend(f"- {value}" for value in values)
        else:
            lines.append(f"- {empty}")
