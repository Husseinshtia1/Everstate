from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .continuity import ContinuationPacket
from .ypipe_fabric import YpipeError, YpipeFabric


@dataclass(frozen=True)
class YpipeContinuationResult:
    mode: str
    target: str
    verified_identity: bool
    response: dict


def continuation_envelope(packet: ContinuationPacket) -> dict:
    return {
        "everstate": {
            "project_id": packet.project_id,
            "state_version": packet.state_version,
            "objective": packet.objective,
            "current_task": packet.current_task,
            "decisions": list(packet.decisions),
            "constraints": list(packet.constraints),
            "failed_attempts": list(packet.failed_attempts),
            "blockers": list(packet.blockers),
            "modified_files": list(packet.modified_files),
            "unresolved_conflicts": list(packet.unresolved_conflicts),
            "next_action": packet.next_action,
            "continuation_prompt": packet.to_prompt(),
        },
        "contract": {
            "canonical_state_authority": "everstate",
            "canonical_state_mutation": "forbidden",
            "repository_evidence_overrides_stale_summary": True,
            "surface_conflicts_instead_of_guessing": True,
        },
    }


def write_ypipe_handoff(root: Path, packet: ContinuationPacket) -> Path:
    directory = root.resolve() / ".everstate" / "handoffs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"state-v{packet.state_version}-ypipe.json"
    path.write_text(
        json.dumps(continuation_envelope(packet), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _identity_matches(response: dict, packet: ContinuationPacket) -> bool:
    project_id = response.get("everstate_project_id")
    state_version = response.get("everstate_state_version")
    return project_id == packet.project_id and state_version == packet.state_version


def _parse_direct_response(content: str) -> dict:
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
        raise YpipeError("Ypipe continuation response was not valid JSON") from exc
    if not isinstance(value, dict):
        raise YpipeError("Ypipe continuation response must be a JSON object")
    return value


def execute_ypipe_continuation(
    fabric: YpipeFabric,
    packet: ContinuationPacket,
    *,
    model: str | None = None,
    smartpipe_endpoint: str | None = None,
    verify_identity: bool = True,
) -> YpipeContinuationResult:
    envelope = continuation_envelope(packet)

    if smartpipe_endpoint:
        response = fabric.run_smartpipe(smartpipe_endpoint, envelope)
        verified = _identity_matches(response, packet)
        if verify_identity and not verified:
            raise YpipeError(
                "Ypipe SmartPipe response did not preserve Everstate project_id/state_version identity"
            )
        return YpipeContinuationResult(
            mode="smartpipe",
            target=smartpipe_endpoint,
            verified_identity=verified,
            response=response,
        )

    selected_model = model or fabric.resolve_model()
    request = {
        "role": "user",
        "content": (
            "Continue from the Everstate packet below. Do not mutate or reinterpret canonical state. "
            "Return JSON only with keys everstate_project_id, everstate_state_version, analysis, "
            "proposed_next_action, conflicts. Preserve project_id and state_version exactly.\n\n"
            + json.dumps(envelope, ensure_ascii=False)
        ),
    }
    answer = fabric.execute(
        model=selected_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a local continuation worker. Everstate is authoritative for project state. "
                    "Repository evidence, if supplied by tools/workflows, outranks stale conversational summaries."
                ),
            },
            request,
        ],
    )
    response = _parse_direct_response(answer.content)
    verified = _identity_matches(response, packet)
    if verify_identity and not verified:
        raise YpipeError("Ypipe inference response did not preserve Everstate project_id/state_version identity")
    return YpipeContinuationResult(
        mode="inference",
        target=selected_model,
        verified_identity=verified,
        response=response,
    )
