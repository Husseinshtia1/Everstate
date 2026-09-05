from everstate.source_access import (
    AccessMethod,
    AccessOption,
    AccessStatus,
    SourceCapabilities,
    claude_desktop_access_baseline,
    rank_access_options,
    recommended_access_option,
)


def test_access_ladder_order_is_stable() -> None:
    options = claude_desktop_access_baseline()
    assert [item.method for item in rank_access_options(options)] == [
        AccessMethod.OFFICIAL_SUPPORTED,
        AccessMethod.AUTHORIZED_SESSION,
        AccessMethod.OFFICIAL_EXPORT,
        AccessMethod.LOCAL_CACHE,
        AccessMethod.MANUAL_IMPORT,
    ]


def test_unverified_authorized_path_is_not_treated_as_ready() -> None:
    options = claude_desktop_access_baseline()
    choice = recommended_access_option(options)
    assert choice is not None
    assert choice.method == AccessMethod.OFFICIAL_EXPORT


def test_live_authorized_path_becomes_primary_when_proven() -> None:
    capabilities = SourceCapabilities(
        list_projects=True,
        read_project_metadata=True,
        read_project_instructions=True,
        list_conversations=True,
        read_conversations=True,
        list_knowledge=True,
        read_knowledge=True,
    )
    options = claude_desktop_access_baseline(
        authorized_session_status=AccessStatus.READY,
        authorized_capabilities=capabilities,
    )
    choice = recommended_access_option(options)
    assert choice is not None
    assert choice.method == AccessMethod.AUTHORIZED_SESSION
    assert choice.capabilities.continuation_ready is True


def test_local_cache_never_silently_escalates() -> None:
    cache = AccessOption(
        source_environment="claude-desktop",
        method=AccessMethod.LOCAL_CACHE,
        status=AccessStatus.PARTIAL,
        capabilities=SourceCapabilities(list_projects=True),
        detail="recovery",
        requires_explicit_approval=True,
    )
    assert recommended_access_option([cache]) is None
    assert recommended_access_option([cache], allow_sensitive_fallback=True) == cache


def test_unavailable_higher_method_does_not_block_lower_usable_method() -> None:
    official = AccessOption(
        source_environment="example",
        method=AccessMethod.OFFICIAL_SUPPORTED,
        status=AccessStatus.UNAVAILABLE,
        capabilities=SourceCapabilities(),
        detail="none",
    )
    authorized = AccessOption(
        source_environment="example",
        method=AccessMethod.AUTHORIZED_SESSION,
        status=AccessStatus.READY,
        capabilities=SourceCapabilities(list_projects=True),
        detail="proven",
    )
    assert recommended_access_option([official, authorized]) == authorized
