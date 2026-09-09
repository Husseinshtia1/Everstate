from __future__ import annotations

import json

import pytest

from everstate.agent_council import (
    CouncilError,
    CouncilMode,
    CouncilParticipant,
    CouncilVerdict,
    execute_agent_council,
)
from everstate.continuity import ContinuationPacket
from everstate.council_cli import _council_state_is_stale
from everstate.provider_fabric import FabricHealth, FabricResponse, FabricTarget


class ScenarioFabric:
    def __init__(self, name: str, responses: list[dict | Exception]):
        self.name = name
        self.responses = list(responses)
        self.calls = 0

    def health(self):
        return FabricHealth("READY", True, "scenario")

    def discover_targets(self):
        return (FabricTarget(id=f"{self.name}-model", provider=self.name, model=f"{self.name}-model"),)

    def execute(self, *, model: str, messages: list[dict], timeout: float | None = None):
        index = min(self.calls, len(self.responses) - 1)
        outcome = self.responses[index]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        payload = {
            "everstate_project_id": outcome.get("project_id", "proj_real"),
            "everstate_state_version": outcome.get("state_version", 11),
            "verdict": outcome.get("verdict"),
            "recommendation": outcome.get("recommendation", "Proceed"),
            "reasoning": outcome.get("reasoning", "Scenario reasoning"),
            "risks": outcome.get("risks", []),
            "evidence": outcome.get("evidence", ["repo:test"]),
            "conflicts": outcome.get("conflicts", []),
            "confidence": outcome.get("confidence", 0.8),
        }
        return FabricResponse(target=model, content=json.dumps(payload), raw=payload)


def packet(*, constraints: list[str] | None = None, version: int = 11) -> ContinuationPacket:
    return ContinuationPacket(
        project_id="proj_real",
        state_version=version,
        objective="Ship a production change safely",
        current_task="Evaluate implementation decision",
        constraints=constraints or [],
        failed_attempts=["Previous migration lost rollback metadata"],
        next_action="Get independent review",
    )


def participant(role: str, fabric: ScenarioFabric, *, local: bool | None = None) -> CouncilParticipant:
    return CouncilParticipant(role=role, fabric=fabric, model=f"{fabric.name}-model", local=local)


def test_scenario_01_architecture_review_semantically_equivalent_approval():
    """Three architects use different wording but reach the same verdict."""
    fabrics = [
        ScenarioFabric("ypipe", [{"verdict": "approve", "recommendation": "Proceed with the modular split"}]),
        ScenarioFabric("free", [{"verdict": "approve", "recommendation": "Yes, ship the split"}]),
        ScenarioFabric("cloud", [{"verdict": "approve", "recommendation": "Go ahead with this architecture"}]),
    ]
    result = execute_agent_council(
        packet=packet(),
        question="Should we split the execution router into policy and transport layers?",
        participants=tuple(participant(role, fabric) for role, fabric in zip(("architect", "critic", "verifier"), fabrics)),
    )
    assert result.consensus == "CONSENSUS: approve"
    assert {opinion.verdict for opinion in result.opinions} == {CouncilVerdict.APPROVE}


def test_scenario_02_security_review_preserves_real_disagreement():
    """Security, product, and operations genuinely disagree."""
    fabrics = [
        ScenarioFabric("a", [{"verdict": "reject", "recommendation": "Do not deploy until token rotation exists"}]),
        ScenarioFabric("b", [{"verdict": "conditional", "recommendation": "Deploy only if feature-flagged"}]),
        ScenarioFabric("c", [{"verdict": "approve", "recommendation": "Proceed; blast radius is acceptable"}]),
    ]
    result = execute_agent_council(
        packet=packet(),
        question="Can we deploy the authentication change tonight?",
        participants=tuple(participant(role, fabric) for role, fabric in zip(("security", "product", "ops"), fabrics)),
    )
    assert result.consensus == "NO_CONSENSUS"
    assert len(result.disagreements) == 2


def test_scenario_03_provider_outage_does_not_destroy_majority_quorum():
    """One remote provider times out while two independent reviewers succeed."""
    healthy_a = ScenarioFabric("ypipe", [{"verdict": "approve"}])
    dead = ScenarioFabric("free", [TimeoutError("provider timed out")])
    healthy_b = ScenarioFabric("cloud", [{"verdict": "approve"}])
    result = execute_agent_council(
        packet=packet(),
        question="Is the incident rollback safe?",
        participants=(participant("operator", healthy_a), participant("critic", dead), participant("verifier", healthy_b)),
    )
    assert result.quorum_met is True
    assert result.consensus == "CONSENSUS: approve"
    assert len(result.failures) == 1
    assert "timed out" in result.failures[0].error


def test_scenario_04_identity_drift_is_excluded_when_quorum_remains():
    """A confused model answers for another project and must not influence the decision."""
    good_a = ScenarioFabric("a", [{"verdict": "approve"}])
    drift = ScenarioFabric("b", [{"project_id": "proj_other", "verdict": "reject"}])
    good_b = ScenarioFabric("c", [{"verdict": "approve"}])
    result = execute_agent_council(
        packet=packet(),
        question="Review the database migration plan",
        participants=(participant("dba", good_a), participant("critic", drift), participant("verifier", good_b)),
    )
    assert result.consensus == "CONSENSUS: approve"
    assert len(result.failures) == 1
    assert "identity drift" in result.failures[0].error
    assert all(opinion.fabric != "b" for opinion in result.opinions)


def test_scenario_05_local_only_is_enforced_inside_core_not_only_cli():
    """A caller cannot bypass NO_CLOUD by constructing remote participants directly."""
    local = ScenarioFabric("ypipe", [{"verdict": "approve"}])
    remote = ScenarioFabric("omniroute", [{"verdict": "approve"}])
    with pytest.raises(CouncilError, match="remote council participants are forbidden"):
        execute_agent_council(
            packet=packet(constraints=["DATA_MUST_NOT_LEAVE_DEVICE"]),
            question="Review private customer data migration",
            participants=(participant("local-reviewer", local, local=True), participant("remote-reviewer", remote, local=False)),
        )
    assert local.calls == 0
    assert remote.calls == 0


def test_scenario_06_duplicate_agent_identity_cannot_double_vote():
    """Configuration mistakes must not let one model count twice."""
    fabric = ScenarioFabric("same", [{"verdict": "approve"}])
    duplicate = participant("reviewer", fabric)
    with pytest.raises(CouncilError, match="unique"):
        execute_agent_council(
            packet=packet(),
            question="Approve this refactor?",
            participants=(duplicate, duplicate),
        )
    assert fabric.calls == 0


def test_scenario_07_multi_round_debate_survives_one_second_round_failure():
    """A reviewer can disappear mid-debate while the majority continues."""
    a = ScenarioFabric("a", [{"verdict": "conditional"}, {"verdict": "approve"}])
    b = ScenarioFabric("b", [{"verdict": "reject"}, TimeoutError("rate limit")])
    c = ScenarioFabric("c", [{"verdict": "conditional"}, {"verdict": "approve"}])
    result = execute_agent_council(
        packet=packet(),
        question="Debate whether to replace the queue implementation",
        participants=(participant("architect", a), participant("critic", b), participant("operator", c)),
        mode=CouncilMode.DEBATE,
        rounds=2,
    )
    final_round = [opinion for opinion in result.opinions if opinion.round == 2]
    assert len(final_round) == 2
    assert result.consensus == "CONSENSUS: approve"
    assert len(result.failures) == 1
    assert result.failures[0].round == 2


def test_scenario_08_evidence_coverage_exposes_unsupported_confidence():
    """A confident answer without evidence is visible instead of looking fully verified."""
    with_evidence = ScenarioFabric("a", [{"verdict": "approve", "evidence": ["tests/test_auth.py::test_refresh"]}])
    no_evidence_a = ScenarioFabric("b", [{"verdict": "approve", "evidence": [], "confidence": 0.99}])
    no_evidence_b = ScenarioFabric("c", [{"verdict": "approve", "evidence": [], "confidence": 0.99}])
    result = execute_agent_council(
        packet=packet(),
        question="Did the regression fix address the real failure?",
        participants=(participant("tester", with_evidence), participant("critic", no_evidence_a), participant("reviewer", no_evidence_b)),
    )
    assert result.evidence_coverage == pytest.approx(1 / 3)
    assert result.average_confidence > 0.9


def test_scenario_09_all_agents_can_abstain_when_evidence_is_missing():
    """The system must not manufacture a decision from three honest abstentions."""
    fabrics = [ScenarioFabric(name, [{"verdict": "abstain", "recommendation": "Need more evidence", "evidence": []}]) for name in ("a", "b", "c")]
    result = execute_agent_council(
        packet=packet(),
        question="Was the production incident caused by the new cache layer?",
        participants=tuple(participant(role, fabric) for role, fabric in zip(("incident", "database", "network"), fabrics)),
    )
    assert result.consensus == "NO_CONSENSUS: all participants abstained"
    assert result.evidence_coverage == 0.0


def test_scenario_10_long_running_review_detects_state_advance():
    """Advice against state v11 becomes stale if another agent advances the project to v12."""
    initial = packet(version=11)
    latest = packet(version=12)
    assert _council_state_is_stale(initial, latest) is True
    assert _council_state_is_stale(initial, packet(version=11)) is False
