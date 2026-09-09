from everstate.fabric_routing import (
    SovereigntyMode,
    choose_execution_fabric,
    constraints_require_local,
    eligible_fabric_order,
)
from everstate.provider_fabric import FabricHealth


READY = FabricHealth(status="READY", ready=True, detail="ready")
DOWN = FabricHealth(status="UNAVAILABLE", ready=False, detail="down")


def test_explicit_local_constraints_are_detected_deterministically() -> None:
    assert constraints_require_local(["NO_CLOUD"]) is True
    assert constraints_require_local(["data must not leave device"]) is True
    assert constraints_require_local(["air-gapped"]) is True
    assert constraints_require_local(["ZERO_CROSS_PROJECT_LEAKAGE"]) is False


def test_local_constraint_selects_ypipe_even_when_cloud_is_ready() -> None:
    decision = choose_execution_fabric(
        constraints=["NO_CLOUD"],
        ypipe_health=READY,
        omniroute_health=READY,
    )
    assert decision.selected == "ypipe"
    assert decision.local_required is True


def test_local_constraint_never_falls_back_to_cloud() -> None:
    decision = choose_execution_fabric(
        constraints=["LOCAL_ONLY"],
        ypipe_health=DOWN,
        omniroute_health=READY,
    )
    assert decision.selected is None
    assert decision.local_required is True
    assert "cloud fallback is forbidden" in decision.reason


def test_auto_prefers_ready_local_fabric() -> None:
    decision = choose_execution_fabric(ypipe_health=READY, omniroute_health=READY)
    assert decision.selected == "ypipe"


def test_auto_falls_back_to_omniroute_when_ypipe_is_down() -> None:
    decision = choose_execution_fabric(ypipe_health=DOWN, omniroute_health=READY)
    assert decision.selected == "omniroute"


def test_cloud_preferred_uses_omniroute_first() -> None:
    decision = choose_execution_fabric(
        mode=SovereigntyMode.CLOUD_PREFERRED,
        ypipe_health=READY,
        omniroute_health=READY,
    )
    assert decision.selected == "omniroute"


def test_no_ready_fabric_returns_none() -> None:
    decision = choose_execution_fabric(ypipe_health=DOWN, omniroute_health=DOWN)
    assert decision.selected is None


def test_auto_exposes_full_runtime_fallback_order() -> None:
    order = eligible_fabric_order(
        ypipe_health=READY,
        freellmapi_health=READY,
        omniroute_health=READY,
    )
    assert order == ("ypipe", "freellmapi", "omniroute")


def test_cloud_preferred_exposes_full_runtime_fallback_order() -> None:
    order = eligible_fabric_order(
        mode=SovereigntyMode.CLOUD_PREFERRED,
        ypipe_health=READY,
        freellmapi_health=READY,
        omniroute_health=READY,
    )
    assert order == ("omniroute", "freellmapi", "ypipe")


def test_local_constraints_remove_remote_fabrics_from_runtime_fallback_order() -> None:
    order = eligible_fabric_order(
        constraints=["DATA_MUST_NOT_LEAVE_DEVICE"],
        ypipe_health=READY,
        freellmapi_health=READY,
        omniroute_health=READY,
    )
    assert order == ("ypipe",)
