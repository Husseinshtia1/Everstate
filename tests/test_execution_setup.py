from __future__ import annotations

import json
import os

from everstate.execution_config import (
    ExecutionSettings,
    configured_policy,
    fabric_enabled,
    load_execution_settings,
    save_execution_settings,
)
from everstate.fabric_routing import SovereigntyMode, choose_execution_fabric
from everstate.provider_fabric import FabricHealth


READY = FabricHealth(status="READY", ready=True, detail="ready")
DOWN = FabricHealth(status="UNAVAILABLE", ready=False, detail="down")


def test_execution_settings_round_trip_with_private_permissions(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EVERSTATE_HOME", str(tmp_path))
    path = save_execution_settings(
        ExecutionSettings(
            policy="local-only",
            ypipe_enabled=True,
            freellmapi_enabled=False,
            freellmapi_api_key="unified-secret",
            omniroute_enabled=False,
        )
    )
    loaded = load_execution_settings()
    assert loaded.policy == "local-only"
    assert loaded.freellmapi_api_key == "unified-secret"
    assert configured_policy() == "local-only"
    assert fabric_enabled("ypipe") is True
    assert fabric_enabled("freellmapi") is False
    assert fabric_enabled("omniroute") is False
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_auto_prefers_free_remote_before_omniroute_when_local_is_down() -> None:
    decision = choose_execution_fabric(
        ypipe_health=DOWN,
        freellmapi_health=READY,
        omniroute_health=READY,
    )
    assert decision.selected == "freellmapi"


def test_cloud_preferred_prefers_omniroute_then_free() -> None:
    decision = choose_execution_fabric(
        mode=SovereigntyMode.CLOUD_PREFERRED,
        ypipe_health=READY,
        freellmapi_health=READY,
        omniroute_health=DOWN,
    )
    assert decision.selected == "freellmapi"


def test_no_cloud_forbids_both_remote_fabrics() -> None:
    decision = choose_execution_fabric(
        constraints=["DATA_MUST_NOT_LEAVE_DEVICE"],
        ypipe_health=DOWN,
        freellmapi_health=READY,
        omniroute_health=READY,
    )
    assert decision.selected is None
    assert decision.local_required is True
    assert "FreeLLMAPI" in decision.reason
    assert "OmniRoute" in decision.reason
