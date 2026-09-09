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


def eligible_fabric_order(
    *,
    constraints: list[str] | tuple[str, ...] = (),
    mode: SovereigntyMode = SovereigntyMode.AUTO,
    ypipe_health: FabricHealth | None = None,
    freellmapi_health: FabricHealth | None = None,
    omniroute_health: FabricHealth | None = None,
) -> tuple[str, ...]:
    """Return every currently ready fabric in policy-safe fallback order.

    Health is only a preflight signal. Runtime execution may still fail after a
    fabric reports READY, so callers that promise automatic failover should try
    the remaining entries in this order. Sovereignty constraints are enforced
    here so remote fabrics can never appear in a local-only fallback plan.
    """
    ready = {
        "ypipe": bool(ypipe_health and ypipe_health.ready),
        "freellmapi": bool(freellmapi_health and freellmapi_health.ready),
        "omniroute": bool(omniroute_health and omniroute_health.ready),
    }
    local_required = mode is SovereigntyMode.LOCAL_ONLY or constraints_require_local(constraints)
    if local_required:
        return ("ypipe",) if ready["ypipe"] else ()

    preferred = (
        ("omniroute", "freellmapi", "ypipe")
        if mode is SovereigntyMode.CLOUD_PREFERRED
        else ("ypipe", "freellmapi", "omniroute")
    )
    return tuple(name for name in preferred if ready[name])


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

    order = eligible_fabric_order(
        constraints=constraints,
        mode=mode,
        ypipe_health=ypipe_health,
        freellmapi_health=freellmapi_health,
        omniroute_health=omniroute_health,
    )

    if local_required:
        if order:
            return result("ypipe", "Canonical constraints require local execution and Ypipe is ready.", local=True)
        return result(
            None,
            "Canonical constraints require local execution, but Ypipe is not ready; cloud fallback is forbidden, including FreeLLMAPI and OmniRoute.",
            local=True,
        )

    if not order:
        return result(None, "No execution fabric is ready.")

    selected = order[0]
    if mode is SovereigntyMode.CLOUD_PREFERRED:
        reasons = {
            "omniroute": "Cloud-preferred mode selected a ready OmniRoute fabric.",
            "freellmapi": "OmniRoute is unavailable; free remote capacity selected before local fallback.",
            "ypipe": "Remote fabrics are unavailable; cloud-preferred mode fell back to local Ypipe.",
        }
    else:
        reasons = {
            "ypipe": "Ready local Ypipe preferred for privacy and provider independence.",
            "freellmapi": "Ypipe is unavailable; ready FreeLLMAPI selected as free remote capacity.",
            "omniroute": "Local and free fabrics are unavailable; ready OmniRoute selected as fallback.",
        }
    return result(selected, reasons[selected])
