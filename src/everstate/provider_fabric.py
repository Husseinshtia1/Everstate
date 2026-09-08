from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FabricTarget:
    id: str
    provider: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class FabricHealth:
    status: str
    ready: bool
    detail: str


@dataclass(frozen=True)
class FabricResponse:
    target: str
    content: str
    raw: dict


class ExecutionFabric(Protocol):
    name: str

    def health(self) -> FabricHealth: ...

    def discover_targets(self) -> tuple[FabricTarget, ...]: ...

    def execute(self, *, model: str, messages: list[dict], timeout: float | None = None) -> FabricResponse: ...
