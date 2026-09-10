from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .agent_council import CouncilMode, CouncilParticipant, CouncilResult
from .continuity import ContinuationPacket
from .fabric_routing import constraints_require_local


class RufloError(RuntimeError):
    pass


@dataclass(frozen=True)
class RufloHealth:
    ready: bool
    version: str | None
    detail: str


@dataclass(frozen=True)
class RufloRun:
    enabled: bool
    version: str | None
    topology: str
    strategy: str
    task_strategy: str
    agents: tuple[str, ...]
    task_registered: bool
    redacted_for_local_only: bool


@dataclass(frozen=True)
class RufloConfig:
    command: tuple[str, ...] | None
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "RufloConfig":
        configured = os.environ.get("EVERSTATE_RUFLO_COMMAND", "").strip()
        if configured:
            command = tuple(shlex.split(configured, posix=os.name != "nt"))
            if not command:
                command = None
        else:
            executable = shutil.which("claude-flow")
            command = (executable,) if executable else None
        raw_timeout = os.environ.get("EVERSTATE_RUFLO_TIMEOUT", "30").strip()
        try:
            timeout = float(raw_timeout)
        except ValueError:
            timeout = 30.0
        return cls(command=command, timeout_seconds=max(1.0, min(timeout, 300.0)))


_SAFE_ENV_KEYS = {
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TMP",
    "TEMP",
    "TMPDIR",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "NODE_PATH",
    "NPM_CONFIG_PREFIX",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
}


class RufloOrchestrator:
    """Local process adapter for Ruflo/claude-flow v3 swarm coordination.

    Ruflo coordinates agent roles and task topology only. Everstate remains the
    canonical state authority and continues to execute/verify model calls via
    ExecutionFabric. Provider credentials are intentionally excluded from the
    Ruflo subprocess environment.
    """

    def __init__(self, config: RufloConfig | None = None):
        self.config = config or RufloConfig.from_env()

    @staticmethod
    def _child_env() -> dict[str, str]:
        source = os.environ
        child = {key: value for key, value in source.items() if key.upper() in _SAFE_ENV_KEYS}
        for key, value in source.items():
            upper = key.upper()
            if not (upper.startswith("RUFLO_") or upper.startswith("CLAUDE_FLOW_")):
                continue
            if any(token in upper for token in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
                continue
            child[key] = value
        return child

    def _run(self, *args: str, cwd: Path | None = None) -> str:
        if not self.config.command:
            raise RufloError("Ruflo is not installed or EVERSTATE_RUFLO_COMMAND is not configured")
        try:
            proc = subprocess.run(
                [*self.config.command, *args],
                cwd=str(cwd) if cwd else None,
                text=True,
                capture_output=True,
                timeout=self.config.timeout_seconds,
                check=False,
                env=self._child_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RufloError(f"Ruflo command failed to start: {exc}") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "unknown Ruflo error").strip()
            raise RufloError(f"Ruflo command failed ({proc.returncode}): {detail[:500]}")
        return (proc.stdout or proc.stderr or "").strip()

    def health(self) -> RufloHealth:
        if not self.config.command:
            return RufloHealth(False, None, "claude-flow executable not found")
        try:
            output = self._run("--version")
        except RufloError as exc:
            return RufloHealth(False, None, str(exc))
        match = re.search(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?", output, flags=re.IGNORECASE)
        if not match:
            return RufloHealth(False, None, f"Could not parse Ruflo version from: {output[:120]}")
        version = ".".join(match.group(index) for index in (1, 2, 3))
        if int(match.group(1)) < 3:
            return RufloHealth(False, version, "Everstate requires Ruflo/claude-flow v3 or newer")
        return RufloHealth(True, version, "Ruflo v3 orchestration ready")

    @staticmethod
    def _agent_type(role: str) -> str:
        normalized = role.strip().lower()
        if any(token in normalized for token in ("test", "verify", "qa")):
            return "tester"
        if any(token in normalized for token in ("research", "investigat")):
            return "researcher"
        if any(token in normalized for token in ("code", "implement", "develop")):
            return "coder"
        if any(token in normalized for token in ("coordinate", "manager", "lead")):
            return "coordinator"
        return "analyst"

    def prepare_council(
        self,
        *,
        root: Path,
        packet: ContinuationPacket,
        question: str,
        participants: Iterable[CouncilParticipant],
        mode: CouncilMode,
    ) -> RufloRun:
        health = self.health()
        if not health.ready:
            raise RufloError(health.detail)
        people = tuple(participants)
        if not people:
            raise RufloError("Cannot create a Ruflo swarm without council participants")

        local_only = constraints_require_local(packet.constraints)
        topology = "mesh" if mode is CouncilMode.DEBATE else "star"
        # Ruflo v3.41.1 accepts domain strategies (analysis, balanced, etc.)
        # for both swarm initialization and task orchestration. Everstate owns
        # the actual parallel model fan-out; Ruflo coordinates the swarm roles.
        swarm_strategy = "balanced" if mode is CouncilMode.DEBATE else "analysis"
        task_strategy = "balanced" if mode is CouncilMode.DEBATE else "analysis"
        self._run(
            "swarm",
            "init",
            "--topology",
            topology,
            "--max-agents",
            str(len(people)),
            "--strategy",
            swarm_strategy,
            cwd=root,
        )

        spawned: list[str] = []
        for participant in people:
            role_name = participant.role[:80]
            self._run(
                "agent",
                "spawn",
                "--type",
                self._agent_type(participant.role),
                "--name",
                f"Everstate {role_name}",
                cwd=root,
            )
            spawned.append(participant.role)

        if local_only:
            task_text = (
                f"Everstate council coordination for {packet.project_id}@{packet.state_version}; "
                f"roles={','.join(spawned)}; content redacted by sovereignty policy"
            )
        else:
            task_text = (
                f"Everstate advisory council {packet.project_id}@{packet.state_version}: {question.strip()} "
                f"Roles: {', '.join(spawned)}. Everstate is canonical state authority; do not mutate project state."
            )
        self._run(
            "task",
            "orchestrate",
            "--task",
            task_text,
            "--strategy",
            task_strategy,
            "--priority",
            "high" if mode is CouncilMode.DEBATE else "medium",
            cwd=root,
        )
        return RufloRun(
            enabled=True,
            version=health.version,
            topology=topology,
            strategy=swarm_strategy,
            task_strategy=task_strategy,
            agents=tuple(spawned),
            task_registered=True,
            redacted_for_local_only=local_only,
        )

    def verify_result(self, *, packet: ContinuationPacket, result: CouncilResult) -> None:
        if result.project_id != packet.project_id or result.state_version != packet.state_version:
            raise RufloError("Ruflo-coordinated council result identity drifted from canonical Everstate state")
        if result.canonical_state_mutated:
            raise RufloError("Ruflo-coordinated council attempted to mutate canonical Everstate state")
