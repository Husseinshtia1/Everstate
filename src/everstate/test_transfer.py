from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .continuity import ContinuationPacket
from .storage import LocalStore
from .transfer_plan import RegisteredProject, SourceEnvironment


@dataclass(frozen=True)
class TestTransferBundle:
    directory: Path
    metadata_path: Path
    markdown_path: Path
    json_path: Path
    state_version: int


def _safe(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value).strip("-") or "value"


def create_test_transfer_bundle(
    store: LocalStore,
    *,
    project: RegisteredProject,
    source: SourceEnvironment,
    destination: str,
    session_id: str | None = None,
    output_root: Path | None = None,
) -> TestTransferBundle:
    """Create an isolated test-transfer artifact without refreshing or mutating canonical state."""
    state = store.latest_state(project.project_id)
    if state is None:
        raise ValueError(f"Project {project.project_id} has no canonical Everstate state to test")

    packet = ContinuationPacket.from_state(state)
    created_at = datetime.now(timezone.utc)
    root = (output_root or (Path.home() / ".everstate" / "test-transfers")).expanduser().resolve()
    stamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    directory = root / f"{stamp}-{_safe(project.project_id)}-{_safe(destination)}"
    suffix = 1
    while directory.exists():
        suffix += 1
        directory = root / f"{stamp}-{_safe(project.project_id)}-{_safe(destination)}-{suffix}"
    directory.mkdir(parents=True, exist_ok=False)

    metadata = {
        "mode": "TEST_ONLY",
        "created_at": created_at.isoformat(),
        "source": source.value,
        "source_session": session_id,
        "destination": destination,
        "project": {
            "id": project.project_id,
            "name": project.name,
            "root_path": str(project.root_path),
        },
        "state_version": state.version,
        "canonical_state_mutated": False,
        "provider_launched": False,
    }

    metadata_path = directory / "transfer-review.json"
    markdown_path = directory / "continuation.md"
    json_path = directory / "continuation.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(packet.to_prompt() + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return TestTransferBundle(
        directory=directory,
        metadata_path=metadata_path,
        markdown_path=markdown_path,
        json_path=json_path,
        state_version=state.version,
    )
