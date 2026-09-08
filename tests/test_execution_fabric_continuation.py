from __future__ import annotations

import json

import pytest

from everstate.continuity import ContinuationPacket
from everstate.execution_fabric_continuation import (
    ExecutionFabricError,
    execute_fabric_continuation,
    resolve_target_model,
)
from everstate.provider_fabric import FabricResponse, FabricTarget


class FakeFabric:
    name = "fake-fabric"

    def __init__(self, *, response: dict | None = None, targets: tuple[str, ...] = ("local-model",)):
        self.response = response or {}
        self.targets = targets
        self.calls: list[dict] = []

    def discover_targets(self):
        return tuple(FabricTarget(id=value, provider="fake", model=value) for value in self.targets)

    def execute(self, *, model: str, messages: list[dict], timeout=None):
        self.calls.append({"model": model, "messages": messages, "timeout": timeout})
        return FabricResponse(target=model, content=json.dumps(self.response), raw={"choices": []})


def packet() -> ContinuationPacket:
    return ContinuationPacket(
        project_id="project-123",
        state_version=7,
        objective="Preserve continuity",
        current_task="Execute through selected fabric",
        decisions=("Everstate remains canonical",),
        constraints=("NO_SECRET_ACCESS",),
        failed_attempts=(),
        blockers=(),
        modified_files=("src/example.py",),
        unresolved_conflicts=(),
        next_action="Run a verified continuation",
    )


def test_executes_with_exact_identity_and_preserves_contract():
    fabric = FakeFabric(
        response={
            "everstate_project_id": "project-123",
            "everstate_state_version": 7,
            "analysis": "ok",
            "proposed_next_action": "continue",
            "conflicts": [],
        }
    )
    result = execute_fabric_continuation(fabric, packet())

    assert result.fabric == "fake-fabric"
    assert result.target == "local-model"
    assert result.verified_identity is True
    assert len(fabric.calls) == 1
    prompt = fabric.calls[0]["messages"][1]["content"]
    assert '"canonical_state_authority": "everstate"' in prompt
    assert '"canonical_state_mutation": "forbidden"' in prompt


def test_rejects_identity_drift_by_default():
    fabric = FakeFabric(
        response={
            "everstate_project_id": "wrong-project",
            "everstate_state_version": 7,
            "analysis": "wrong identity",
            "proposed_next_action": "continue",
            "conflicts": [],
        }
    )

    with pytest.raises(ExecutionFabricError, match="did not preserve Everstate"):
        execute_fabric_continuation(fabric, packet())


def test_can_report_unverified_identity_only_when_explicitly_allowed():
    fabric = FakeFabric(
        response={
            "everstate_project_id": "wrong-project",
            "everstate_state_version": 7,
        }
    )

    result = execute_fabric_continuation(fabric, packet(), verify_identity=False)
    assert result.verified_identity is False


def test_requested_model_must_exist_in_live_catalog():
    fabric = FakeFabric(targets=("model-a", "model-b"))

    assert resolve_target_model(fabric, "model-b") == "model-b"
    with pytest.raises(ExecutionFabricError, match="not in the live"):
        resolve_target_model(fabric, "missing-model")


def test_rejects_non_json_continuation_output():
    class BadFabric(FakeFabric):
        def execute(self, *, model: str, messages: list[dict], timeout=None):
            return FabricResponse(target=model, content="not-json", raw={})

    with pytest.raises(ExecutionFabricError, match="not valid JSON"):
        execute_fabric_continuation(BadFabric(), packet())
