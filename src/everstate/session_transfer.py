from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .source_discovery import AssociationStatus, DiscoveredSession, associate_session, discover_sessions
from .storage import LocalStore
from .transfer_plan import SourceEnvironment, TransferPlan, build_transfer_plan, list_registered_projects


@dataclass(frozen=True)
class SessionTransferReview:
    plan: TransferPlan
    session: DiscoveredSession
    association_status: AssociationStatus
    association_detail: str
    project_selection: str

    def summary(self) -> str:
        project = self.plan.projects[0]
        lines = [
            "EVERSTATE SESSION TRANSFER REVIEW",
            f"SOURCE: {self.plan.source.value}",
            f"SOURCE SESSION: {self.session.session_id}",
            f"SOURCE WORKDIR: {self.session.working_directory or 'unknown'}",
            f"ASSOCIATION: {self.association_status.value}",
            f"PROJECT: {project.name} [{project.project_id}]",
            f"PROJECT ROOT: {project.root_path}",
            f"PROJECT SELECTION: {self.project_selection}",
            f"DESTINATION: {self.plan.destination}",
            "MODE: review-only",
        ]
        return "\n".join(lines)


def _find_session(source: SourceEnvironment, session_id: str, *, home: Path | None = None) -> DiscoveredSession:
    session_id = session_id.strip()
    if not session_id:
        raise ValueError("Source session id is required")
    matches = [session for session in discover_sessions(source, home) if session.session_id == session_id]
    if not matches:
        raise ValueError(f"Unknown {source.value} session: {session_id}")
    if len(matches) > 1:
        paths = ", ".join(str(session.storage_path) for session in matches[:5])
        raise ValueError(f"Ambiguous session id {session_id!r}; matching files: {paths}")
    return matches[0]


def build_session_transfer_review(
    store: LocalStore,
    *,
    source: SourceEnvironment,
    destination: str,
    session_id: str,
    project_selector: str | None = None,
    home: Path | None = None,
) -> SessionTransferReview:
    if source not in {SourceEnvironment.CODEX, SourceEnvironment.CLAUDE_CODE}:
        raise ValueError(
            f"Session-aware discovery is not enabled for {source.value}; choose the project explicitly instead"
        )

    session = _find_session(source, session_id, home=home)
    projects = list_registered_projects(store)
    association = associate_session(session, projects)

    selector = project_selector.strip() if project_selector else None
    selection = "explicit-user"
    if selector is None:
        if association.status is not AssociationStatus.VERIFIED or association.project is None:
            raise ValueError(
                f"Session association is {association.status.value}; specify --project explicitly before transfer"
            )
        selector = association.project.project_id
        selection = "verified-session-metadata"

    plan = build_transfer_plan(
        store,
        source=source,
        destination=destination,
        project_selectors=[selector],
    )
    selected = plan.projects[0]

    if association.status is AssociationStatus.VERIFIED and association.project is not None:
        if selected.project_id != association.project.project_id:
            raise ValueError(
                "Explicit project conflicts with verified session metadata; Everstate will not override a verified association"
            )
    elif association.status is AssociationStatus.AMBIGUOUS and association.candidates:
        candidate_ids = {candidate.project_id for candidate in association.candidates}
        if selected.project_id not in candidate_ids:
            raise ValueError(
                "Explicit project is not one of the session's candidate projects; inspect the source session before transfer"
            )

    return SessionTransferReview(
        plan=plan,
        session=session,
        association_status=association.status,
        association_detail=association.detail,
        project_selection=selection,
    )
