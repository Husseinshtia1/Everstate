from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ClaimType(StrEnum):
    FACT = "fact"
    GOAL = "goal"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    HYPOTHESIS = "hypothesis"
    ATTEMPT = "attempt"
    FAILURE = "failure"
    SUCCESS = "success"
    TASK = "task"
    RISK = "risk"
    DEPENDENCY = "dependency"
    ARTIFACT_STATE = "artifact_state"


class ClaimStatus(StrEnum):
    CURRENT = "current"
    VERIFIED = "verified"
    INFERRED = "inferred"
    UNVERIFIED = "unverified"
    CONFLICTED = "conflicted"
    STALE = "stale"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class Event(BaseModel):
    id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}")
    project_id: str
    event_type: str
    source_type: str
    source_locator: str | None = None
    actor: str = "system"
    timestamp: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = None


class Evidence(BaseModel):
    id: str = Field(default_factory=lambda: f"ev_{uuid4().hex}")
    project_id: str
    event_id: str
    source_type: str
    source_locator: str | None = None
    excerpt: str | None = None
    authority: str = "observed"
    created_at: datetime = Field(default_factory=utc_now)


class Claim(BaseModel):
    id: str = Field(default_factory=lambda: f"cl_{uuid4().hex}")
    project_id: str
    subject: str
    predicate: str
    value: str
    claim_type: ClaimType
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    authority: str = "inferred"
    valid_from: datetime = Field(default_factory=utc_now)
    valid_until: datetime | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    verified_at: datetime | None = None


class ProjectState(BaseModel):
    project_id: str
    version: int = 1
    objective: str | None = None
    current_task: str | None = None
    active_constraints: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    failed_attempts: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    modified_files: list[str] = Field(default_factory=list)
    next_action: str | None = None
    unresolved_conflicts: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)
