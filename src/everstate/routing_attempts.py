from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .provider_readiness import ProviderProbeResult, ProviderState
from .routing import RankedProvider


@dataclass(frozen=True)
class RoutingAttempt:
    project_id: str
    state_version: int
    target_key: str
    target_name: str
    routing_mode: str
    routing_score: float
    selected_by: str
    result: str
    failure_class: str | None
    returncode: int | None
    started_at: str
    finished_at: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_launch_outcome(
    returncode: int | None,
    post_probe: ProviderProbeResult | None,
) -> ProviderState | None:
    if returncode in {None, 0}:
        return None
    if post_probe is not None and not post_probe.ready:
        return post_probe.state
    return ProviderState.UNKNOWN_FAILURE


def append_routing_attempt(root: Path, attempt: RoutingAttempt) -> Path:
    directory = root.resolve() / ".everstate"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "routing-history.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(attempt), sort_keys=True) + "\n")
    return path


def next_eligible_after_failure(
    ranked: list[RankedProvider],
    failed_keys: set[str],
) -> RankedProvider | None:
    for item in ranked:
        if item.probe.key in failed_keys:
            continue
        if item.routing.eligible:
            return item
    return None
