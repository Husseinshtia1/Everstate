from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from .continuity import ContinuationPacket
from .provider_fabric import FabricResponse, FabricTarget
from .ypipe_continuation import continuation_envelope


class ExecutionFabricError(RuntimeError):
    """Raised when a selected execution fabric cannot preserve the Everstate contract."""


class ExecutionFabric(Protocol):
    name: str

    def discover_targets(self) -> tuple[FabricTarget, ...]: ...

    def execute(
        self,
        *,
        model: str,
        messages: list[dict],
        timeout: float | None = None,
    ) -> FabricResponse: ...


@dataclass(frozen=True)
class ExecutionFabricContinuationResult:
    fabric: str
    target: str
    verified_identity: bool
    response: dict


def _parse_json_object(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            lines = lines[1:-1]
            if lines and lines[0].strip().lower() == "json":
                lines = lines[1:]
            text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExecutionFabricError("Execution fabric continuation response was not valid JSON") from exc
    if not isinstance(value, dict):
        raise ExecutionFabricError("Execution fabric continuation response must be a JSON object")
    return value


def _identity_matches(response: dict, packet: ContinuationPacket) -> bool:
    return (
        response.get("everstate_project_id") == packet.project_id
        and response.get("everstate_state_version") == packet.state_version
    )


def resolve_target_model(fabric: ExecutionFabric, requested_model: str | None = None) -> str:
    targets = fabric.discover_targets()
    available = {target.id for target in targets}
    if requested_model:
        if requested_model not in available:
            raise ExecutionFabricError(
                f"Requested model {requested_model!r} is not in the live {fabric.name} model catalog"
            )
        return requested_model
    if not targets:
        raise ExecutionFabricError(f"{fabric.name} reported no executable models")
    return targets[0].id


def execute_fabric_continuation(
    fabric: ExecutionFabric,
    packet: ContinuationPacket,
    *,
    model: str | None = None,
    verify_identity: bool = True,
) -> ExecutionFabricContinuationResult:
    selected_model = resolve_target_model(fabric, model)
    envelope = continuation_envelope(packet)
    response = fabric.execute(
        model=selected_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an Everstate execution worker. Everstate is the sole authority for canonical "
                    "project state. Do not mutate, rewrite, or silently reinterpret that state. Repository "
                    "evidence outranks stale conversational summaries. Surface conflicts rather than guessing."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Continue from the canonical Everstate packet below. Return JSON only with keys "
                    "everstate_project_id, everstate_state_version, analysis, proposed_next_action, conflicts. "
                    "Preserve project_id and state_version exactly. Do not claim canonical state was changed.\n\n"
                    + json.dumps(envelope, ensure_ascii=False)
                ),
            },
        ],
    )
    decoded = _parse_json_object(response.content)
    verified = _identity_matches(decoded, packet)
    if verify_identity and not verified:
        raise ExecutionFabricError(
            f"{fabric.name} continuation response did not preserve Everstate project_id/state_version identity"
        )
    return ExecutionFabricContinuationResult(
        fabric=fabric.name,
        target=selected_model,
        verified_identity=verified,
        response=decoded,
    )
