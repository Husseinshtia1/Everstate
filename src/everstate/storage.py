from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import Event, ProjectState


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_locator TEXT,
    actor TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_project_timestamp
ON events(project_id, timestamp);

CREATE TABLE IF NOT EXISTS state_versions (
    project_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(project_id, version),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
"""


class LocalStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path.expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_project(self, project_id: str, name: str, root_path: Path) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO projects(id, name, root_path)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    root_path=excluded.root_path,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (project_id, name, str(root_path.resolve())),
            )

    def get_project_by_root(self, root_path: Path) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM projects WHERE root_path = ?",
                (str(root_path.resolve()),),
            ).fetchone()

    def append_event(self, event: Event) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO events(
                    id, project_id, event_type, source_type, source_locator,
                    actor, timestamp, payload_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.project_id,
                    event.event_type,
                    event.source_type,
                    event.source_locator,
                    event.actor,
                    event.timestamp.isoformat(),
                    json.dumps(event.payload, sort_keys=True),
                    event.content_hash,
                ),
            )

    def list_events(self, project_id: str, limit: int = 200) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM events
                WHERE project_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()

    def latest_state(self, project_id: str) -> ProjectState | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT state_json FROM state_versions
                WHERE project_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return ProjectState.model_validate_json(row["state_json"])

    def save_state(self, state: ProjectState) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO state_versions(project_id, version, state_json)
                VALUES (?, ?, ?)
                """,
                (state.project_id, state.version, state.model_dump_json()),
            )
