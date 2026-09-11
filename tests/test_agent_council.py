from __future__ import annotations

import json

import pytest

from everstate.agent_council import (
    CouncilError,
    CouncilMode,
    CouncilParticipant,
    execute_agent_council,
)
from everstate.continuity import ContinuationPacket
from everstate.provider_fabric import FabricHealth, FabricResponse, FabricTarget


class FakeFabric:
    def __init__(self, name: str, recommendation: str, *, project_id: str = "proj_test", state_version: int = 7):
        self.name = name
        self.recommendation = recommendation
        self.project_id = project_id
        self.state_version = state_version
        self.calls: list[list[dict]] = []

    def health(self):
        return FabricHealth("READY", True, "test")

    def discover_targets(self):
        return (FabricTarget(id=f"{self.name}-model", provider=self.name, model=f"{self.name}-model"),)

    def execute(self, *, model: str, messages: list[dict], timeout: float | None = None):
        self.calls.append(messages)
        payload = {
            "everstate_project_id": self.project_id,
            "everstate_state_version": self.state_version,
            "recommendation": self.recommendation,
            "reasoning": f"reasoning from {self.name}",
            "risks": [f"risk-{self.name}"],
            "evidence": [f"evidence-{self.name}"],
            "conflicts": [],
            "confidence": 0.8,
        }
        return FabricResponse(target=model, content=json.dumps(payload), raw=payload)


class FailoverFabric(FakeFabric):
    def __init__(self, *, fail_models: set[str], drift_models: set[str] | None = None):
        super().__init__("freellmapi", "approve")
        self.fail_models = fail_models
        self.drift_models = drift_models or set()
        self.models_called: list[str] = []

    def discover_targets(self):
        return tuple(
            FabricTarget(id=model, provider=self.name, model=model)
            for model in ("primary-a", "primary-b", "fallback-a", "fallback-b", "fallback-c", "fallback-d")
        )

    def execute(self, *, model: str, messages: list[dict], timeout: float | None = None):
        self.models_called.append(model)
        if model in self.fail_models:
            raise RuntimeError('FreeLLMAPI HTTP 429: {"error":{"code":"rate_limit_exceeded"}}')
        payload = {
            "everstate_project_id": "proj_other" if model in self.drift_models else self.project_id,
            "everstate_state_version": self.state_version,
            "recommendation": self.recommendation,
            "reasoning": f"reasoning from {model}",
            "risks": [],
            "evidence": [f"evidence-{model}"],
            "conflicts": [],
            "confidence": 0.9,
        }
        return FabricResponse(target=model, content=json.dumps(payload), raw=payload)


def packet() -> ContinuationPacket:
    return ContinuationPacket(
        project_id="proj_test",
        state_version=7,
        objective="Ship safely",
        current_task="Choose architecture",
        constraints=["Do not mutate canonical state from AI output"],
        next_action="Review architecture",
    )


def test_parallel_review_collects_independent_verified_opinions():
    first = FakeFabric("local", "approve")
    second = FakeFabric("remote", "approve")
    result = execute_agent_council(
        packet=packet(),
        question="Should we proceed?",
        participants=(
            CouncilParticipant("architect", first, "local-model"),
            CouncilParticipant("critic", second, "remote-model"),
        ),
    )

    assert result.consensus == "CONSENSUS: approve"
    assert len(result.opinions) == 2
    assert result.average_confidence == pytest.approx(0.8)
    assert result.canonical_state_mutated is False
    assert {opinion.role for opinion in result.opinions} == {"architect", "critic"}


def test_debate_runs_multiple_rounds_and_shares_prior_opinions():
    first = FakeFabric("a", "approve")
    second = FakeFabric("b", "revise")
    result = execute_agent_council(
        packet=packet(),
        question="Debate this architecture",
        participants=(
            CouncilParticipant("architect", first, "a-model"),
            CouncilParticipant("critic", second, "b-model"),
        ),
        mode=CouncilMode.DEBATE,
        rounds=2,
    )

    assert len(result.opinions) == 4
    assert len(first.calls) == 2
    assert len(second.calls) == 2
    second_round_prompt = first.calls[1][1]["content"]
    assert "PRIOR COUNCIL OPINIONS TO CRITIQUE" in second_round_prompt
    assert "critic:b:b-model" in second_round_prompt
    assert result.consensus == "NO_CONSENSUS"


def test_identity_drift_is_rejected():
    drifting = FakeFabric("drift", "approve", project_id="proj_other")
    with pytest.raises(CouncilError, match="identity drift"):
        execute_agent_council(
            packet=packet(),
            question="Check identity",
            participants=(CouncilParticipant("verifier", drifting, "drift-model"),),
        )


def test_fenced_json_is_accepted():
    class FencedFabric(FakeFabric):
        def execute(self, *, model: str, messages: list[dict], timeout: float | None = None):
            self.calls.append(messages)
            payload = {
                "everstate_project_id": self.project_id,
                "everstate_state_version": self.state_version,
                "recommendation": self.recommendation,
                "reasoning": "ok",
                "risks": [],
                "evidence": [],
                "conflicts": [],
                "confidence": 1,
            }
            return FabricResponse(target=model, content=f"```json\n{json.dumps(payload)}\n```", raw=payload)

    fabric = FencedFabric("fenced", "approve")
    result = execute_agent_council(
        packet=packet(),
        question="Check fenced JSON",
        participants=(CouncilParticipant("reviewer", fabric, "fenced-model"),),
    )
    assert result.consensus == "CONSENSUS: approve"


def test_rate_limited_roles_fail_over_to_distinct_ready_models():
    fabric = FailoverFabric(fail_models={"primary-a", "primary-b"})
    result = execute_agent_council(
        packet=packet(),
        question="Review despite cooldowns",
        participants=(
            CouncilParticipant("architect", fabric, "primary-a"),
            CouncilParticipant("critic", fabric, "primary-b"),
        ),
        min_successful=2,
    )

    assert result.quorum_met is True
    assert {opinion.model for opinion in result.opinions} == {"fallback-a", "fallback-b"}
    assert all(opinion.fabric == "freellmapi" for opinion in result.opinions)


def test_identity_drift_does_not_try_alternate_model():
    fabric = FailoverFabric(fail_models=set(), drift_models={"primary-a"})
    with pytest.raises(CouncilError, match="quorum not met") as excinfo:
        execute_agent_council(
            packet=packet(),
            question="Do not mask identity drift",
            participants=(CouncilParticipant("architect", fabric, "primary-a", alternates=("fallback-a",)),),
        )

    assert "identity drift" in str(excinfo.value)
    assert fabric.models_called == ["primary-a"]
