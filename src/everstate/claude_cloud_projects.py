from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_UUID_TEXT = re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b")
_NAME_PATTERNS = (
    re.compile(r'(?i)"(?:name|title|display_name|displayName)"\s*:\s*"([^"\\]{1,160})"'),
    re.compile(r"(?i)'(?:name|title|display_name|displayName)'\s*:\s*'([^'\\]{1,160})'"),
)
_PROJECT_MARKER = re.compile(r"(?i)project")
_EXCLUDED_NAMES = {
    "project", "projects", "project id", "project_id", "project uuid", "project_uuid",
    "claude", "claude.ai", "organization", "organizations", "name", "title",
}


@dataclass(frozen=True)
class ClaudeCloudProjectCandidate:
    project_id: str
    name: str | None
    confidence: str
    source_file: Path
    evidence: tuple[str, ...]

    @property
    def selectable(self) -> bool:
        return self.confidence == "STRICT"


def _indexeddb_roots(home: Path | None = None) -> tuple[Path, ...]:
    home = (home or Path.home()).expanduser()
    roots = [
        home / ".config" / "Claude" / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb",
        home / "Library" / "Application Support" / "Claude" / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb",
    ]
    return tuple(root for root in roots if root.is_dir())


def _decode_window(data: bytes) -> str:
    # Preserve printable ASCII while replacing binary separators with spaces. This is
    # intentionally not a general IndexedDB decoder and does not expose whole records.
    chars = []
    for byte in data:
        if 32 <= byte <= 126:
            chars.append(chr(byte))
        else:
            chars.append(" ")
    return "".join(chars)


def _candidate_name(window: str, project_id: str) -> str | None:
    candidates: list[str] = []
    for pattern in _NAME_PATTERNS:
        for match in pattern.finditer(window):
            value = match.group(1).strip()
            if not value or value.lower() in _EXCLUDED_NAMES:
                continue
            if project_id.lower() in value.lower():
                continue
            if value.startswith("http://") or value.startswith("https://"):
                continue
            candidates.append(value)
    if not candidates:
        return None
    # Prefer the shortest human-readable metadata field; long values are more likely
    # to be message/instruction fragments than project names.
    return sorted(set(candidates), key=lambda value: (len(value), value.lower()))[0]


def _scan_file(path: Path, *, max_file_bytes: int, window_bytes: int) -> list[ClaudeCloudProjectCandidate]:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            data = handle.read(min(size, max_file_bytes))
    except OSError:
        return []

    text = _decode_window(data)
    found: list[ClaudeCloudProjectCandidate] = []
    for match in _UUID_TEXT.finditer(text):
        project_id = match.group(0).lower()
        start = max(0, match.start() - window_bytes)
        end = min(len(text), match.end() + window_bytes)
        window = text[start:end]
        if not _PROJECT_MARKER.search(window):
            continue
        name = _candidate_name(window, project_id)
        confidence = "STRICT" if name is not None else "UNVERIFIED"
        evidence = ["uuid_near_project_marker"]
        if name is not None:
            evidence.append("name_or_title_in_same_window")
        found.append(
            ClaudeCloudProjectCandidate(
                project_id=project_id,
                name=name,
                confidence=confidence,
                source_file=path,
                evidence=tuple(evidence),
            )
        )
    return found


def discover_claude_cloud_project_candidates(
    home: Path | None = None,
    *,
    max_total_bytes: int = 32 * 1024 * 1024,
    max_file_bytes: int = 8 * 1024 * 1024,
    window_bytes: int = 1536,
) -> list[ClaudeCloudProjectCandidate]:
    """Extract project-like metadata candidates from Claude Desktop's local cloud cache.

    Safety contract:
    - Reads only the claude.ai IndexedDB files, never Cookies or Local Storage.
    - Emits only UUID, optional name/title metadata, confidence, and source filename.
    - STRICT requires UUID + project marker + name/title in one bounded window.
    - UNVERIFIED candidates are never automatically selectable by transfer UX.
    """
    total = 0
    by_id: dict[str, ClaudeCloudProjectCandidate] = {}
    for root in _indexeddb_roots(home):
        try:
            files: Iterable[Path] = sorted(path for path in root.iterdir() if path.is_file())
        except OSError:
            continue
        for path in files:
            if total >= max_total_bytes:
                break
            try:
                size = path.stat().st_size
            except OSError:
                continue
            allowed = min(size, max_file_bytes, max_total_bytes - total)
            if allowed <= 0:
                break
            total += allowed
            for candidate in _scan_file(path, max_file_bytes=allowed, window_bytes=window_bytes):
                previous = by_id.get(candidate.project_id)
                if previous is None:
                    by_id[candidate.project_id] = candidate
                    continue
                # Prefer STRICT over UNVERIFIED, then a named candidate over unnamed.
                rank = (candidate.confidence == "STRICT", candidate.name is not None)
                prev_rank = (previous.confidence == "STRICT", previous.name is not None)
                if rank > prev_rank:
                    by_id[candidate.project_id] = candidate
    return sorted(
        by_id.values(),
        key=lambda item: (item.confidence != "STRICT", (item.name or "").lower(), item.project_id),
    )
