from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .continuity import ContinuationPacket


PORTABLE_FORMAT = "everstate.continuation.v1"


@dataclass(frozen=True)
class PortableExportResult:
    markdown_path: Path
    json_path: Path


def portable_json(packet: ContinuationPacket) -> dict:
    return {
        "format": PORTABLE_FORMAT,
        "project_id": packet.project_id,
        "state_version": packet.state_version,
        "continuation": packet.model_dump(mode="json"),
    }


def portable_markdown(packet: ContinuationPacket) -> str:
    return (
        "# Everstate Portable Continuation\n\n"
        f"Format: `{PORTABLE_FORMAT}`  \n"
        f"Project: `{packet.project_id}`  \n"
        f"State version: `{packet.state_version}`\n\n"
        "This file is a portable continuation artifact. Give it to another AI, tool, device, or human collaborator. "
        "The continuation packet below is authoritative only for the recorded state version; inspect newer repository evidence before acting.\n\n"
        "```text\n"
        + packet.to_prompt()
        + "\n```\n"
    )


def export_packet(
    root: Path,
    packet: ContinuationPacket,
    output_dir: Path | None = None,
) -> PortableExportResult:
    directory = (output_dir or (root.resolve() / ".everstate" / "exports")).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"everstate-state-v{packet.state_version}"
    markdown_path = directory / f"{stem}.md"
    json_path = directory / f"{stem}.json"
    markdown_path.write_text(portable_markdown(packet), encoding="utf-8")
    json_path.write_text(json.dumps(portable_json(packet), indent=2) + "\n", encoding="utf-8")
    return PortableExportResult(markdown_path=markdown_path, json_path=json_path)


def _clipboard_command() -> list[str] | None:
    candidates = [
        (["wl-copy"], "wl-copy"),
        (["xclip", "-selection", "clipboard"], "xclip"),
        (["xsel", "--clipboard", "--input"], "xsel"),
        (["pbcopy"], "pbcopy"),
    ]
    for command, executable in candidates:
        resolved = shutil.which(executable)
        if resolved:
            return [resolved, *command[1:]]
    return None


def copy_packet(packet: ContinuationPacket) -> str | None:
    command = _clipboard_command()
    if command is None:
        return None
    subprocess.run(
        command,
        input=packet.to_prompt(),
        text=True,
        check=True,
        capture_output=True,
    )
    return command[0]
