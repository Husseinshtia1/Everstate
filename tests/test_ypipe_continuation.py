from __future__ import annotations

import json

import pytest

from everstate.continuity import ContinuationPacket
from everstate.provider_fabric import FabricResponse, FabricTarget
from everstate.ypipe_continuation import continuation_envelope, execute_ypipe_continuation
from everstate.ypipe_fabric import YpipeError


class FakeFabric:
    def __init__(self, *, direct_response: dict | None = None, smartpipe_response: dict | None = None):
        self.direct_response = direct_response
        self.smartpipe_response = smartpipe_response
        self.executed = None
        self.smartpipe = None

    def discover_targets(self):
        return (FabricTarget(id="local/model", provider="ypipe", model="local/model"),)

    def resolve_model(self):
        return "local/model"

    def execute(self, *, model, messages, timeout=None):
        self.executed = {"model": model, "messages": messages}
        return FabricResponse(
            target=model,
            content=json.dumps(self.direct_response),
            raw={"choices": []},
        )

    def run_smartpipe(self, endpoint, payload, timeout=None):
        self.smartpipe = {"endpoint": endpoint, "payload": payload}
        return dict(self.smartpipe_response)


def _packet() -> ContinuationPacket:
    return ContinuationPacket(
        project_id="proj_123",
        state_version=9,
        objective="KEEP_PROJECT_TRUTH",
        current_task="CONTINUE_LOCALLY",
        constraints=["NO_CLOUD", "ZERO_CROSS_PROJECT_LEAKAGE"],
        next_action="VERIFY_BEFORE_EDIT",
    )


def test_envelope_preserves_canonical_fields_and_authority_boundary() -> None:
    envelope = continuation_envelope(_packet())
    assert envelope["everstate"]["project_id"] == "proj_123"
    assert envelope["everstate"]["state_version"] == 9
    assert envelope["everstate"]["constraints"] == ["NO_CLOUD", "ZERO_CROSS_PROJECT_LEAKAGE"]
    assert envelope["contract"]["canonical_state_authority"] == "everstate"
    assert envelope["contract"]["canonical_state_mutation"] == "forbidden"


def test_direct_inference_requires_matching_identity() -> None:
    fabric = FakeFabric(
        direct_response={
            "everstate_project_id": "proj_123",
            "everstate_state_version": 9,
            "analysis": "ready",
            "proposed_next_action": "VERIFY_BEFORE_EDIT",
            "conflicts": [],
        }
    )
    result = execute_ypipe_continuation(fabric, _packet())
    assert result.mode == "inference"
    assert result.target == "local/model"
    assert result.verified_identity is True
    prompt = fabric.executed["messages"][1]["content"]
    assert "canonical_state_mutation" in prompt
    assert "proj_123" in prompt
    assert "NO_CLOUD" in prompt


def test_direct_inference_rejects_wrong_project_identity() -> None:
    fabric = FakeFabric(
        direct_response={
            "everstate_project_id": "proj_OTHER",
            "everstate_state_version": 9,
            "analysis": "wrong project",
        }
    )
    with pytest.raises(YpipeError, match="did not preserve"):
        execute_ypipe_continuation(fabric, _packet())


def test_direct_inference_rejects_wrong_state_version() -> None:
    fabric = FakeFabric(
        direct_response={
            "everstate_project_id": "proj_123",
            "everstate_state_version": 8,
        }
    )
    with pytest.raises(YpipeError, match="did not preserve"):
        execute_ypipe_continuation(fabric, _packet())


def test_smartpipe_receives_structured_envelope_and_verifies_identity() -> None:
    fabric = FakeFabric(
        smartpipe_response={
            "everstate_project_id": "proj_123",
            "everstate_state_version": 9,
            "status": "continued",
        }
    )
    result = execute_ypipe_continuation(
        fabric,
        _packet(),
        smartpipe_endpoint="/everstate/continue",
    )
    assert result.mode == "smartpipe"
    assert result.verified_identity is True
    assert fabric.smartpipe["endpoint"] == "/everstate/continue"
    assert fabric.smartpipe["payload"]["everstate"]["current_task"] == "CONTINUE_LOCALLY"


def test_smartpipe_wrong_identity_is_blocked() -> None:
    fabric = FakeFabric(
        smartpipe_response={
            "everstate_project_id": "proj_123",
            "everstate_state_version": 10,
        }
    )
    with pytest.raises(YpipeError, match="SmartPipe response did not preserve"):
        execute_ypipe_continuation(
            fabric,
            _packet(),
            smartpipe_endpoint="/everstate/continue",
        )


def test_unverified_diagnostic_mode_is_explicit() -> None:
    fabric = FakeFabric(
        direct_response={
            "everstate_project_id": "wrong",
            "everstate_state_version": 1,
        }
    )
    result = execute_ypipe_continuation(fabric, _packet(), verify_identity=False)
    assert result.verified_identity is False
