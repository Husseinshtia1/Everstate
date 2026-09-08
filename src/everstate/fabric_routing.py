from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .provider_fabric import FabricHealth


class SovereigntyMode(StrEnum):
    AUTO = "auto"
    LOCAL_ONLY = "local-only"
    CLOUD_ALLOWED = "cloud-allowed"
    CLOUD_PREFERRED = "cloud-preferred"


@dataclass(frozen=True)
class FabricRoutingDecision:
    selected: str | None
    reason: str
    local_required: bool
    ypipe_ready: bool
    omniroute_ready: bool


_LOCAL_CONSTRAINTS = {
    "NO_CLOUD",
    "LOCAL_ONLY",
    "AIRGAPPED",
    "AIR_GAPPED",
    "DATA_MUST_NOT_LEAVE_DEVICE",
    "DATA_MUST_NOT_LEAVE_MACHINE",
    "LOCAL_EXECUTION_ONLY",
}


def constraints_require_local(constraints: list[str] | tuple[str, ...]) -> bool:
    normalized = {value.strip().upper().replace("-", "_").replace(" ", "_") for value in constraints}
    return bool(normalized & _LOCAL_CONSTRAINTS)


def choose_execution_fabric(
    *,
    constraints: list[str] | tuple[str, ...] = (),
    mode: SovereigntyMode = SovereigntyMode.AUTO,
    ypipe_health: FabricHealth | None = None,
    omniroute_health: FabricHealth | None = None,
) -> FabricRoutingDecision:
    ypipe_ready = bool(ypipe_health and ypipe_health.ready)
    omniroute_ready = bool(omniroute_health and omniroute_health.ready)
    local_required = mode is SovereigntyMode.LOCAL_ONLY or constraints_require_local(constraints)

    if local_required:
        if ypipe_ready:
            return FabricRoutingDecision(
                selected="ypipe",
                reason="Canonical constraints require local execution and Ypipe is ready.",
                local_required=True,
                ypipe_ready=ypipe_ready,
                omniroute_ready=omniroute_ready,
            )
        return FabricRoutingDecision(
            selected=None,
            reason="Canonical constraints require local execution, but Ypipe is not ready; cloud fallback is forbidden.",
            local_required=True,
            ypipe_ready=ypipe_ready,
            omniroute_ready=omniroute_ready,
        )

    if mode is SovereigntyMode.CLOUD_PREFERRED:
        if omniroute_ready:
            selected = "omniroute"
            reason = "Cloud-preferred mode selected a ready OmniRoute fabric."
        elif ypipe_ready:
            selected = "ypipe"
            reason = "Cloud-preferred mode fell back to ready local Ypipe because OmniRoute is unavailable."
        else:
            selected = None
            reason = "No execution fabric is ready."
    else:
        # AUTO and CLOUD_ALLOWED intentionally prefer local execution when it is
        # available, preserving privacy/cost without forbidding cloud fallback.
        if ypipe_ready:
            selected = "ypipe"
            reason = "Ready local Ypipe preferred for privacy and provider independence."
        elif omniroute_ready:
            selected = "omniroute"
            reason = "Ypipe is unavailable; ready OmniRoute selected as allowed fallback."
        else:
            selected = None
            reason = "No execution fabric is ready."

    return FabricRoutingDecision(
        selected=selected,
        reason=reason,
        local_required=False,
        ypipe_ready=ypipe_ready,
        omniroute_ready=omniroute_ready,
    )
