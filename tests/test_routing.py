from __future__ import annotations

from everstate.provider_readiness import (
    ProviderCapability,
    ProviderProbeResult,
    ProviderState,
)
from everstate.routing import RoutingMode, rank_providers, recommended_provider, score_provider


def probe(
    key: str,
    *,
    state: ProviderState = ProviderState.READY,
    coding: bool = True,
    repo: bool = True,
    local: bool = False,
    cloud: bool = True,
    manual: bool = False,
) -> ProviderProbeResult:
    return ProviderProbeResult(
        key=key,
        name=key,
        state=state,
        detail="test",
        executable=f"/tmp/{key}" if not manual else None,
        capability=ProviderCapability(
            coding_agent=coding,
            repository_access=repo,
            local=local,
            cloud=cloud,
            manual=manual,
        ),
    )


def test_unready_provider_fails_hard_gate() -> None:
    result = probe("codex", state=ProviderState.AUTH_EXPIRED)
    score = score_provider(result)

    assert score.eligible is False
    assert score.score == 0.0
    assert "AUTH_EXPIRED" in score.reason


def test_auto_prefers_ready_coding_agent_over_manual_fallback() -> None:
    cloud = probe("codex")
    manual = probe("manual", coding=False, repo=False, cloud=False, manual=True, state=ProviderState.ALWAYS_READY)

    ranked = rank_providers([manual, cloud], RoutingMode.AUTO)

    assert ranked[0].probe.key == "codex"
    assert ranked[0].recommended is True
    assert ranked[1].probe.key == "manual"


def test_manual_is_recommended_when_all_integrated_targets_are_unavailable() -> None:
    codex = probe("codex", state=ProviderState.AUTH_EXPIRED)
    claude = probe("claude", state=ProviderState.LIMIT_REACHED)
    manual = probe("manual", coding=False, repo=False, cloud=False, manual=True, state=ProviderState.ALWAYS_READY)

    recommendation = recommended_provider([codex, claude, manual], RoutingMode.AUTO)

    assert recommendation is not None
    assert recommendation.key == "manual"


def test_local_first_changes_preference_without_bypassing_hard_gates() -> None:
    cloud = probe("cloud")
    local = probe("local", local=True, cloud=False)

    auto = rank_providers([cloud, local], RoutingMode.AUTO)
    local_first = rank_providers([cloud, local], RoutingMode.LOCAL_FIRST)

    assert auto[0].probe.key in {"cloud", "local"}
    assert local_first[0].probe.key == "local"
    assert local_first[0].routing.mode_modifier > 0


def test_cloud_best_prefers_cloud_when_both_are_ready() -> None:
    cloud = probe("cloud")
    local = probe("local", local=True, cloud=False)

    ranked = rank_providers([local, cloud], RoutingMode.CLOUD_BEST)

    assert ranked[0].probe.key == "cloud"
    assert ranked[0].recommended is True


def test_ask_me_ranks_but_never_auto_recommends() -> None:
    cloud = probe("cloud")
    local = probe("local", local=True, cloud=False)

    ranked = rank_providers([cloud, local], RoutingMode.ASK_ME)

    assert any(item.rank is not None for item in ranked)
    assert all(item.recommended is False for item in ranked)
    assert recommended_provider([cloud, local], RoutingMode.ASK_ME) is None
