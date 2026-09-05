from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .service import EverstateService


@dataclass(frozen=True)
class EmergencyFailoverBundle:
    project_id: str
    state_version: int
    source_provider: str
    target_provider: str
    project_root: Path
    markdown_path: Path
    json_path: Path
    manifest_path: Path
    source_contacted: bool = False


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare_emergency_failover(
    *,
    service: EverstateService,
    root: Path,
    source_provider: str,
    target_provider: str,
    output_root: Path | None = None,
) -> EmergencyFailoverBundle:
    """Create a continuation bundle without contacting the failed source provider.

    This function has no source-provider adapter parameter by design. Its only inputs
    are Everstate canonical state plus the requested destination identity.
    """
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project root does not exist or is not a directory: {root}")
    source_provider = source_provider.strip().lower()
    target_provider = target_provider.strip().lower()
    if not source_provider or not target_provider:
        raise ValueError("source_provider and target_provider are required")
    if source_provider == target_provider:
        raise ValueError("emergency failover target must differ from the unavailable source provider")

    packet = service.continuation_packet(root)
    state = service.status(root)
    base = (output_root or (Path.home() / ".everstate" / "failovers")).expanduser().resolve()
    bundle_dir = base / f"{_now_stamp()}-{packet.project_id}-{target_provider}"
    bundle_dir.mkdir(parents=True, exist_ok=False)

    packet_json = packet.model_dump(mode="json") if hasattr(packet, "model_dump") else packet.__dict__
    json_payload = {
        "schema": "everstate.emergency_failover.v1",
        "project_id": packet.project_id,
        "state_version": packet.state_version,
        "project_root": str(root),
        "source_provider": source_provider,
        "source_status": "UNAVAILABLE",
        "source_contacted_during_failover": False,
        "target_provider": target_provider,
        "canonical_state": state.model_dump(mode="json"),
        "continuation_packet": packet_json,
    }
    json_bytes = (json.dumps(json_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    json_path = bundle_dir / "continuation.json"
    json_path.write_bytes(json_bytes)

    markdown = "\n".join(
        [
            "# EVERSTATE EMERGENCY CONTINUATION",
            "",
            f"Project ID: {packet.project_id}",
            f"State version: {packet.state_version}",
            f"Project root: {root}",
            f"Unavailable source: {source_provider}",
            f"Destination: {target_provider}",
            "Source contacted during failover: NO",
            "",
            packet.to_prompt(),
            "",
        ]
    )
    markdown_bytes = markdown.encode("utf-8")
    markdown_path = bundle_dir / "continuation.md"
    markdown_path.write_bytes(markdown_bytes)

    manifest = {
        "schema": "everstate.failover_manifest.v1",
        "project_id": packet.project_id,
        "state_version": packet.state_version,
        "source_provider": source_provider,
        "target_provider": target_provider,
        "source_contacted": False,
        "files": {
            "continuation.json": _sha256(json_bytes),
            "continuation.md": _sha256(markdown_bytes),
        },
    }
    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return EmergencyFailoverBundle(
        project_id=packet.project_id,
        state_version=packet.state_version,
        source_provider=source_provider,
        target_provider=target_provider,
        project_root=root,
        markdown_path=markdown_path,
        json_path=json_path,
        manifest_path=manifest_path,
        source_contacted=False,
    )
