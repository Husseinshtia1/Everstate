from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .continuity import ContinuationPacket
from .providers import ProviderAdapter


@dataclass(frozen=True)
class HandoffResult:
    path: Path
    command: list[str]
    launched: bool
    returncode: int | None = None


def write_handoff(root: Path, packet: ContinuationPacket, target: ProviderAdapter) -> Path:
    directory = root.resolve() / ".everstate" / "handoffs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"state-v{packet.state_version}-{target.executable}.md"
    path.write_text(packet.to_prompt() + "\n", encoding="utf-8")
    return path


def prepare_handoff(root: Path, packet: ContinuationPacket, target: ProviderAdapter) -> HandoffResult:
    path = write_handoff(root, packet, target)
    prompt = (
        "Continue this existing project from the Everstate continuation packet below. "
        "Inspect the current working tree before modifying files. If repository evidence conflicts "
        "with the packet, surface the conflict instead of silently guessing.\n\n"
        + packet.to_prompt()
    )
    return HandoffResult(path=path, command=target.interactive_command(prompt), launched=False)


def launch_handoff(root: Path, packet: ContinuationPacket, target: ProviderAdapter) -> HandoffResult:
    prepared = prepare_handoff(root, packet, target)
    prompt = prepared.command[-1]
    returncode = target.launch(root, prompt)
    return HandoffResult(
        path=prepared.path,
        command=prepared.command,
        launched=True,
        returncode=returncode,
    )
