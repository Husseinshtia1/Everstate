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
    freellmapi_ready: bool
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
    freellmapi_health: FabricHealth | None = None,
    omniroute_health: FabricHealth | None = None,
) -> FabricRoutingDecision:
    ypipe_ready = bool(ypipe_health and ypipe_health.ready)
    freellmapi_ready = bool(freellmapi_health and freellmapi_health.ready)
    omniroute_ready = bool(omniroute_health and omniroute_health.ready)
    local_required = mode is SovereigntyMode.LOCAL_ONLY or constraints_require_local(constraints)

    def result(selected: str | None, reason: str, *, local: bool = False) -> FabricRoutingDecision:
        return FabricRoutingDecision(
            selected=selected,
            reason=reason,
            local_required=local,
            ypipe_ready=ypipe_ready,
            freellmapi_ready=freellmapi_ready,
            omniroute_ready=omniroute_ready,
        )

    if local_required:
        if ypipe_ready:
            return result("ypipe", "Canonical constraints require local execution and Ypipe is ready.", local=True)
        return result(
            None,
            "Canonical constraints require local execution, but Ypipe is not ready; all remote fallback is forbidden.",
            local=True,
        )

    if mode is SovereigntyMode.CLOUD_PREFERRED:
        if omniroute_ready:
            return result("omniroute", "Cloud-preferred mode selected a ready OmniRoute fabric.")
        if freellmapi_ready:
            return result("freellmapi", "OmniRoute is unavailable; free remote capacity selected before local fallback.")
        if ypipe_ready:
            return result("ypipe", "Remote fabrics are unavailable; cloud-preferred mode fell back to local Ypipe.")
        return result(None, "No execution fabric is ready.")

    # AUTO/CLOUD_ALLOWED minimize data egress and cost: local first, then free
    # remote capacity, then general cloud routing.
    if ypipe_ready:
        return result("ypipe", "Ready local Ypipe preferred for privacy and provider independence.")
    if freellmapi_ready:
        return result("freellmapi", "Ypipe is unavailable; ready FreeLLMAPI selected as free remote capacity.")
    if omniroute_ready:
        return result("omniroute", "Local and free fabrics are unavailable; ready OmniRoute selected as fallback.")
    return result(None, "No execution fabric is ready.")
