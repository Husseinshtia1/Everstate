from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class AccessMethod(str, Enum):
    OFFICIAL_SUPPORTED = "official_supported"
    AUTHORIZED_SESSION = "authorized_session"
    OFFICIAL_EXPORT = "official_export"
    LOCAL_CACHE = "local_cache"
    MANUAL_IMPORT = "manual_import"


class AccessStatus(str, Enum):
    READY = "READY"
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNVERIFIED = "UNVERIFIED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class SourceCapabilities:
    list_projects: bool = False
    read_project_metadata: bool = False
    read_project_instructions: bool = False
    list_conversations: bool = False
    read_conversations: bool = False
    list_knowledge: bool = False
    read_knowledge: bool = False

    @property
    def continuation_ready(self) -> bool:
        return (
            self.list_projects
            and self.read_project_metadata
            and self.list_conversations
            and self.read_conversations
        )


@dataclass(frozen=True)
class AccessOption:
    source_environment: str
    method: AccessMethod
    status: AccessStatus
    capabilities: SourceCapabilities
    detail: str
    requires_explicit_approval: bool = False

    @property
    def usable(self) -> bool:
        return self.status in {AccessStatus.READY, AccessStatus.AVAILABLE, AccessStatus.PARTIAL}


_METHOD_PRIORITY = {
    AccessMethod.OFFICIAL_SUPPORTED: 0,
    AccessMethod.AUTHORIZED_SESSION: 1,
    AccessMethod.OFFICIAL_EXPORT: 2,
    AccessMethod.LOCAL_CACHE: 3,
    AccessMethod.MANUAL_IMPORT: 4,
}

_STATUS_PRIORITY = {
    AccessStatus.READY: 0,
    AccessStatus.AVAILABLE: 1,
    AccessStatus.PARTIAL: 2,
    AccessStatus.UNVERIFIED: 3,
    AccessStatus.UNAVAILABLE: 4,
}


def rank_access_options(options: Iterable[AccessOption]) -> list[AccessOption]:
    """Rank source-access paths without inventing readiness.

    Method order expresses Everstate's preferred access ladder. Status is used only
    within the same method. An unverified higher method remains visible but is not
    treated as usable merely because it ranks earlier conceptually.
    """
    return sorted(
        options,
        key=lambda option: (
            _METHOD_PRIORITY[option.method],
            _STATUS_PRIORITY[option.status],
            option.source_environment.lower(),
        ),
    )


def recommended_access_option(
    options: Iterable[AccessOption],
    *,
    allow_sensitive_fallback: bool = False,
) -> AccessOption | None:
    """Return the safest currently usable access path.

    LOCAL_CACHE is deliberately approval-gated. A failed/absent authorized path must
    never silently escalate Everstate into local application cache inspection.
    """
    for option in rank_access_options(options):
        if not option.usable:
            continue
        if option.requires_explicit_approval and not allow_sensitive_fallback:
            continue
        return option
    return None


def claude_desktop_access_baseline(
    *,
    authorized_session_status: AccessStatus = AccessStatus.UNVERIFIED,
    authorized_capabilities: SourceCapabilities | None = None,
    local_cache_status: AccessStatus = AccessStatus.PARTIAL,
) -> list[AccessOption]:
    """Current conservative Claude Desktop access inventory.

    The authorized-session path is intentionally UNVERIFIED by default. Everstate may
    only upgrade it after a live probe proves access on the user's machine. The local
    cache path is recovery-only and approval-gated.
    """
    return [
        AccessOption(
            source_environment="claude-desktop",
            method=AccessMethod.OFFICIAL_SUPPORTED,
            status=AccessStatus.UNVERIFIED,
            capabilities=SourceCapabilities(),
            detail="No verified public Claude Projects API capability has been recorded by Everstate yet.",
        ),
        AccessOption(
            source_environment="claude-desktop",
            method=AccessMethod.AUTHORIZED_SESSION,
            status=authorized_session_status,
            capabilities=authorized_capabilities or SourceCapabilities(),
            detail="Use the user's explicitly authorized existing Claude account/session when a live probe proves the required capabilities.",
        ),
        AccessOption(
            source_environment="claude-desktop",
            method=AccessMethod.OFFICIAL_EXPORT,
            status=AccessStatus.AVAILABLE,
            capabilities=SourceCapabilities(read_project_metadata=True, read_conversations=True),
            detail="User-controlled Claude data export/import path. Exact Project reconstruction remains capability-tested, not assumed.",
        ),
        AccessOption(
            source_environment="claude-desktop",
            method=AccessMethod.LOCAL_CACHE,
            status=local_cache_status,
            capabilities=SourceCapabilities(),
            detail="Local Desktop cache/recovery path. Current live work proved cache presence but not reliable Project reconstruction.",
            requires_explicit_approval=True,
        ),
        AccessOption(
            source_environment="claude-desktop",
            method=AccessMethod.MANUAL_IMPORT,
            status=AccessStatus.AVAILABLE,
            capabilities=SourceCapabilities(),
            detail="User-supplied portable/manual source data. Always explicit and never inferred.",
        ),
    ]
