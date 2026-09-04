from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .provider_readiness import ProviderProbeResult


class RoutingMode(StrEnum):
    AUTO = "auto"
    LOCAL_FIRST = "local-first"
    CLOUD_BEST = "cloud-best"
    ASK_ME = "ask-me"


@dataclass(frozen=True)
class RoutingScore:
    provider_key: str
    eligible: bool
    score: float
    readiness: float
    task_fit: float
    context_fit: float
    tool_fit: float
    privacy_fit: float
    cost_fit: float
    latency_fit: float
    mode_modifier: float
    reason: str


@dataclass(frozen=True)
class RankedProvider:
    probe: ProviderProbeResult
    routing: RoutingScore
    rank: int | None
    recommended: bool = False


def _component_values(result: ProviderProbeResult) -> tuple[float, float, float, float, float, float, float]:
    capability = result.capability

    readiness = 1.0 if result.ready else 0.0
    task_fit = 1.0 if capability.coding_agent else (0.25 if capability.manual else 0.4)
    context_fit = 0.85 if capability.coding_agent else (0.55 if capability.manual else 0.65)
    tool_fit = 1.0 if capability.repository_access else 0.0

    if capability.local:
        privacy_fit = 1.0
        cost_fit = 0.9
        latency_fit = 0.75
    elif capability.manual:
        privacy_fit = 0.9
        cost_fit = 1.0
        latency_fit = 0.6
    else:
        privacy_fit = 0.5
        cost_fit = 0.5
        latency_fit = 0.8

    return readiness, task_fit, context_fit, tool_fit, privacy_fit, cost_fit, latency_fit


def score_provider(result: ProviderProbeResult, mode: RoutingMode = RoutingMode.AUTO) -> RoutingScore:
    if not result.ready:
        return RoutingScore(
            provider_key=result.key,
            eligible=False,
            score=0.0,
            readiness=0.0,
            task_fit=0.0,
            context_fit=0.0,
            tool_fit=0.0,
            privacy_fit=0.0,
            cost_fit=0.0,
            latency_fit=0.0,
            mode_modifier=0.0,
            reason=f"Hard gate failed: {result.state.value}",
        )

    readiness, task_fit, context_fit, tool_fit, privacy_fit, cost_fit, latency_fit = _component_values(result)

    score = (
        readiness * 30.0
        + task_fit * 25.0
        + context_fit * 15.0
        + tool_fit * 10.0
        + privacy_fit * 10.0
        + cost_fit * 5.0
        + latency_fit * 5.0
    )

    mode_modifier = 0.0
    if mode is RoutingMode.LOCAL_FIRST:
        if result.capability.local:
            mode_modifier = 8.0
        elif result.capability.cloud:
            mode_modifier = -4.0
    elif mode is RoutingMode.CLOUD_BEST:
        if result.capability.cloud and not result.capability.manual:
            mode_modifier = 5.0
        elif result.capability.local:
            mode_modifier = -2.0

    score = max(0.0, min(100.0, score + mode_modifier))
    return RoutingScore(
        provider_key=result.key,
        eligible=True,
        score=score,
        readiness=readiness,
        task_fit=task_fit,
        context_fit=context_fit,
        tool_fit=tool_fit,
        privacy_fit=privacy_fit,
        cost_fit=cost_fit,
        latency_fit=latency_fit,
        mode_modifier=mode_modifier,
        reason="Eligible; deterministic routing score computed from explicit v1 weights.",
    )


def rank_providers(
    results: list[ProviderProbeResult],
    mode: RoutingMode = RoutingMode.AUTO,
) -> list[RankedProvider]:
    scored = [(result, score_provider(result, mode)) for result in results]
    eligible = [(result, score) for result, score in scored if score.eligible]
    ineligible = [(result, score) for result, score in scored if not score.eligible]

    eligible.sort(key=lambda item: (-item[1].score, item[0].key))
    ineligible.sort(key=lambda item: item[0].key)

    recommended_key: str | None = None
    if mode is not RoutingMode.ASK_ME and eligible:
        non_manual = [item for item in eligible if not item[0].capability.manual]
        recommended_key = (non_manual[0] if non_manual else eligible[0])[0].key

    ranked: list[RankedProvider] = []
    for index, (result, score) in enumerate(eligible, start=1):
        ranked.append(
            RankedProvider(
                probe=result,
                routing=score,
                rank=index,
                recommended=result.key == recommended_key,
            )
        )
    for result, score in ineligible:
        ranked.append(RankedProvider(probe=result, routing=score, rank=None, recommended=False))
    return ranked


def recommended_provider(
    results: list[ProviderProbeResult],
    mode: RoutingMode = RoutingMode.AUTO,
) -> ProviderProbeResult | None:
    for ranked in rank_providers(results, mode):
        if ranked.recommended:
            return ranked.probe
    return None
