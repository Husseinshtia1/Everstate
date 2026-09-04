from __future__ import annotations

import json
from pathlib import Path

from everstate.provider_readiness import ProviderCapability, ProviderProbeResult, ProviderState
from everstate.routing import RoutingMode, rank_providers
from everstate.routing_attempts import (
    RoutingAttempt,
    append_routing_attempt,
    classify_launch_outcome,
    next_eligible_after_failure,
)


def probe(key: str, state: ProviderState = ProviderState.READY, *, manual: bool = False) -> ProviderProbeResult:
    return ProviderProbeResult(
        key=key,
        name=key,
        state=state,
        detail="test",
        executable=None if manual else f"/tmp/{key}",
        capability=ProviderCapability(
            coding_agent=not manual,
            repository_access=not manual,
            cloud=not manual,
            manual=manual,
        ),
    )


def test_failed_launch_uses_post_probe_failure_class() -> None:
    post_probe = probe("codex", ProviderState.AUTH_EXPIRED)

    failure = classify_launch_outcome(1, post_probe)

    assert failure is ProviderState.AUTH_EXPIRED


def test_failed_launch_without_new_probe_evidence_is_unknown() -> None:
    post_probe = probe("codex", ProviderState.READY)

    failure = classify_launch_outcome(2, post_probe)

    assert failure is ProviderState.UNKNOWN_FAILURE


def test_zero_exit_is_not_classified_as_failure() -> None:
    assert classify_launch_outcome(0, None) is None


def test_next_target_excludes_failed_provider_and_keeps_manual_last_resort() -> None:
    ranked = rank_providers(
        [
            probe("codex"),
            probe("claude"),
            probe("manual", ProviderState.ALWAYS_READY, manual=True),
        ],
        RoutingMode.AUTO,
    )

    next_target = next_eligible_after_failure(ranked, {ranked[0].probe.key})

    assert next_target is not None
    assert next_target.probe.key != ranked[0].probe.key
    assert next_target.routing.eligible is True


def test_routing_attempt_is_appended_outside_project_truth(tmp_path: Path) -> None:
    attempt = RoutingAttempt(
        project_id="proj_test",
        state_version=12,
        target_key="codex",
        target_name="Codex",
        routing_mode="auto",
        routing_score=91.0,
        selected_by="recommended",
        result="FAILED",
        failure_class="AUTH_EXPIRED",
        returncode=1,
        started_at="2026-09-05T00:00:00+00:00",
        finished_at="2026-09-05T00:00:01+00:00",
    )

    path = append_routing_attempt(tmp_path, attempt)

    assert path == tmp_path / ".everstate" / "routing-history.jsonl"
    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["target_key"] == "codex"
    assert record["failure_class"] == "AUTH_EXPIRED"
    assert record["state_version"] == 12
