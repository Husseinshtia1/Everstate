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
    open_projects_ui: bool = False
    open_exact_project: bool = False
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

    UI navigation capabilities are tracked separately from programmatic content access.
    A successful exact-project deep link must not be promoted into list/read capability.
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
            detail="Use the user's explicitly authorized existing Claude account/session when live probes prove each capability.",
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
