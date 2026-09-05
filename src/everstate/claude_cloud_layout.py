from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_UUID_ASCII = re.compile(rb"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b")
_PROJECT_ASCII = re.compile(rb"(?i)project")
_NAME_ASCII = re.compile(rb"(?i)(?:name|title|display_name|displayName)")


@dataclass(frozen=True)
class ClaudeCloudLayoutDiagnosis:
    profile_root: Path
    files_scanned: int
    bytes_scanned: int
    uuid_ascii: int
    uuid_utf16le: int
    project_ascii: int
    project_utf16le: int
    name_ascii: int
    name_utf16le: int
    uuid_with_project_1536: int
    uuid_with_project_4096: int
    uuid_with_project_16384: int
    uuid_with_project_65536: int
    uuid_with_name_4096: int
    truncated: bool


def _roots(home: Path | None = None) -> tuple[tuple[Path, Path], ...]:
    home = (home or Path.home()).expanduser()
    pairs = [
        (home / ".config" / "Claude", home / ".config" / "Claude" / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb"),
        (
            home / "Library" / "Application Support" / "Claude",
            home / "Library" / "Application Support" / "Claude" / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb",
        ),
    ]
    return tuple(pairs)


def _utf16le_literal(text: str) -> bytes:
    return text.encode("utf-16le")


def _count_near(positions_a: list[int], positions_b: list[int], radius: int) -> int:
    if not positions_a or not positions_b:
        return 0
    positions_b = sorted(positions_b)
    count = 0
    j = 0
    for pos in sorted(positions_a):
        while j < len(positions_b) and positions_b[j] < pos - radius:
            j += 1
        k = j
        hit = False
        while k < len(positions_b) and positions_b[k] <= pos + radius:
            hit = True
            break
        if hit:
            count += 1
    return count


def diagnose_claude_cloud_layout(
    home: Path | None = None,
    *,
    max_total_bytes: int = 32 * 1024 * 1024,
    max_file_bytes: int = 8 * 1024 * 1024,
) -> list[ClaudeCloudLayoutDiagnosis]:
    """Describe local claude.ai IndexedDB layout using counts only.

    This deliberately does not emit UUID values, project names, cached records,
    messages, cookies, tokens, instructions, or conversation text.
    """
    results: list[ClaudeCloudLayoutDiagnosis] = []
    for profile_root, indexeddb_root in _roots(home):
        files_scanned = 0
        bytes_scanned = 0
        truncated = False
        uuid_ascii_positions: list[int] = []
        project_ascii_positions: list[int] = []
        name_ascii_positions: list[int] = []
        uuid_utf16le = 0
        project_utf16le = 0
        name_utf16le = 0
        global_offset = 0

        try:
            files = sorted(path for path in indexeddb_root.iterdir() if path.is_file()) if indexeddb_root.is_dir() else []
        except OSError:
            files = []

        for path in files:
            if bytes_scanned >= max_total_bytes:
                truncated = True
                break
            try:
                size = path.stat().st_size
            except OSError:
                continue
            read_limit = min(size, max_file_bytes, max_total_bytes - bytes_scanned)
            if read_limit <= 0:
                truncated = True
                break
            try:
                with path.open("rb") as handle:
                    data = handle.read(read_limit)
            except OSError:
                continue

            files_scanned += 1
            bytes_scanned += len(data)
            if size > read_limit:
                truncated = True

            uuid_ascii_positions.extend(global_offset + match.start() for match in _UUID_ASCII.finditer(data))
            project_ascii_positions.extend(global_offset + match.start() for match in _PROJECT_ASCII.finditer(data))
            name_ascii_positions.extend(global_offset + match.start() for match in _NAME_ASCII.finditer(data))

            # UTF-16LE counts are intentionally literal/structural only. UUIDs are detected
            # by decoding ASCII UUID candidates to their UTF-16LE byte form when possible.
            lowered = data.lower()
            project_utf16le += lowered.count(_utf16le_literal("project"))
            name_utf16le += sum(
                lowered.count(_utf16le_literal(marker))
                for marker in ("name", "title", "display_name", "displayname")
            )

            # Detect generic UTF-16LE UUID shapes without extracting or printing values.
            # Pattern: hex ASCII bytes separated by NULs, with normal UUID hyphens.
            utf16_uuid_pattern = re.compile(
                rb"(?i)(?:[0-9a-f]\x00){8}-\x00(?:[0-9a-f]\x00){4}-\x00(?:[1-5][0-9a-f]{3})".replace(rb"[0-9a-f]{3}", rb"(?:[0-9a-f]\x00){3}")
                + rb"-\x00(?:[89ab]\x00)(?:[0-9a-f]\x00){3}-\x00(?:[0-9a-f]\x00){12}"
            )
            uuid_utf16le += len(utf16_uuid_pattern.findall(data))
            global_offset += len(data) + 1

        results.append(
            ClaudeCloudLayoutDiagnosis(
                profile_root=profile_root,
                files_scanned=files_scanned,
                bytes_scanned=bytes_scanned,
                uuid_ascii=len(uuid_ascii_positions),
                uuid_utf16le=uuid_utf16le,
                project_ascii=len(project_ascii_positions),
                project_utf16le=project_utf16le,
                name_ascii=len(name_ascii_positions),
                name_utf16le=name_utf16le,
                uuid_with_project_1536=_count_near(uuid_ascii_positions, project_ascii_positions, 1536),
                uuid_with_project_4096=_count_near(uuid_ascii_positions, project_ascii_positions, 4096),
                uuid_with_project_16384=_count_near(uuid_ascii_positions, project_ascii_positions, 16384),
                uuid_with_project_65536=_count_near(uuid_ascii_positions, project_ascii_positions, 65536),
                uuid_with_name_4096=_count_near(uuid_ascii_positions, name_ascii_positions, 4096),
                truncated=truncated,
            )
        )
    return results
