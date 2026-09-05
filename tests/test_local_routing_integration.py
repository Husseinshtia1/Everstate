from __future__ import annotations

from everstate.provider_readiness import ProviderCapability, ProviderProbeResult, ProviderState
from everstate.routing import RoutingMode, rank_providers


def _probe(key: str, *, local: bool = False, cloud: bool = True) -> ProviderProbeResult:
    return ProviderProbeResult(
        key=key,
        name=key,
        state=ProviderState.READY,
        detail="ready",
        executable=f"/tmp/{key}",
        capability=ProviderCapability(
            coding_agent=True,
            repository_access=True,
            local=local,
            cloud=cloud,
        ),
    )


def test_local_first_prefers_ready_codex_ollama_over_ready_cloud_targets() -> None:
    ranked = rank_providers(
        [
            _probe("codex"),
            _probe("gemini"),
            _probe("codex-ollama", local=True, cloud=False),
        ],
        RoutingMode.LOCAL_FIRST,
    )

    assert ranked[0].probe.key == "codex-ollama"
    assert ranked[0].recommended is True


def test_auto_mode_does_not_force_local_target() -> None:
    ranked = rank_providers(
        [
            _probe("codex"),
            _probe("codex-ollama", local=True, cloud=False),
        ],
        RoutingMode.AUTO,
    )

    assert ranked[0].routing.eligible is True
    assert {item.probe.key for item in ranked[:2]} == {"codex", "codex-ollama"}
