from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from .service import EverstateService


class ValidationCommand(BaseModel):
    command: list[str]
    expected_exit: int = 0


class ContinuityScenario(BaseModel):
    name: str
    objective: str
    current_task: str
    decisions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    failed_attempts: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_action: str
    required_changed_files: list[str] = Field(default_factory=list)
    protected_files: list[str] = Field(default_factory=list)
    forbidden_substrings: dict[str, list[str]] = Field(default_factory=dict)
    validation_commands: list[ValidationCommand] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "ContinuityScenario":
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))


class AcceptanceCheck(BaseModel):
    name: str
    passed: bool
    details: str


class AcceptanceReport(BaseModel):
    scenario: str
    passed: bool
    score: float
    checks: list[AcceptanceCheck]


def _is_internal_or_generated(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    return (
        normalized in {".everstate", ".claude-flow"}
        or normalized.startswith(".everstate/")
        or normalized.startswith(".claude-flow/")
        or "__pycache__" in parts
        or normalized.endswith(".pyc")
    )


def _add_changed_path(changed: set[str], path: str) -> None:
    normalized = path.replace("\\", "/")
    if normalized and not _is_internal_or_generated(normalized):
        changed.add(normalized)


def _decode_nul_paths(payload: bytes) -> list[str]:
    return [part.decode("utf-8", errors="surrogateescape") for part in payload.split(b"\0") if part]


def _detect_acceptance_baseline(root: Path) -> str | None:
    history = subprocess.run(
        ["git", "log", "--format=%H%x09%s", "--all"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if history.returncode == 0:
        for line in history.stdout.splitlines():
            sha, separator, subject = line.partition("\t")
            if separator and subject == "Acceptance baseline" and sha:
                return sha

    # An agent may amend/rewrite HEAD. Git's reflog normally retains the
    # original baseline object, allowing acceptance to compare against the
    # actual pre-agent repository rather than trusting the rewritten history.
    reflog = subprocess.run(
        ["git", "reflog", "--all", "--format=%H%x09%gs"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if reflog.returncode == 0:
        for line in reflog.stdout.splitlines():
            sha, separator, subject = line.partition("\t")
            if separator and "Acceptance baseline" in subject and sha:
                return sha
    return None


def _git_changed_files(root: Path, baseline_ref: str | None = None) -> set[str]:
    changed: set[str] = set()
    effective_baseline = baseline_ref or _detect_acceptance_baseline(root)

    if effective_baseline:
        # Compare the complete current tree/index/worktree to the immutable
        # baseline object. This still works if the coding agent committed or
        # amended its changes, and -z preserves spaces/non-ASCII filenames.
        tracked = subprocess.run(
            ["git", "diff", "--name-only", "--no-renames", "-z", effective_baseline, "--"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        for path in _decode_nul_paths(tracked.stdout):
            _add_changed_path(changed, path)
    else:
        status = subprocess.run(
            ["git", "status", "--porcelain", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        # Porcelain v1 -z records status bytes followed by a path. For ordinary
        # entries the first three bytes are "XY ". Rename records contain a
        # second NUL-delimited path; treating both paths as evidence is safe.
        records = status.stdout.split(b"\0")
        for record in records:
            if len(record) >= 4:
                _add_changed_path(
                    changed,
                    record[3:].decode("utf-8", errors="surrogateescape"),
                )

    # Untracked files are not included by `git diff <baseline>`, so collect
    # them separately with NUL framing. Git-ignored runtime artifacts remain
    # excluded by both Git and Everstate's internal-artifact filter.
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    for path in _decode_nul_paths(untracked.stdout):
        _add_changed_path(changed, path)
    return changed


def seed_scenario(service: EverstateService, root: Path, scenario: ContinuityScenario) -> str:
    """Populate Everstate with a deterministic interrupted-task state for a benchmark."""
    service.init_project(root)
    service.set_objective(root, scenario.objective)
    service.set_task(root, scenario.current_task)
    for value in scenario.decisions:
        service.add_decision(root, value)
    for value in scenario.constraints:
        service.add_constraint(root, value)
    for value in scenario.failed_attempts:
        service.add_failure(root, value)
    for value in scenario.blockers:
        service.add_blocker(root, value)
    service.set_next_action(root, scenario.next_action)
    return service.continuation_text(root)


def evaluate_scenario(
    root: Path,
    scenario: ContinuityScenario,
    *,
    baseline_ref: str | None = None,
) -> AcceptanceReport:
    root = root.resolve()
    changed = _git_changed_files(root, baseline_ref=baseline_ref)
    checks: list[AcceptanceCheck] = []

    for path in scenario.required_changed_files:
        present = path in changed
        checks.append(
            AcceptanceCheck(
                name=f"required-change:{path}",
                passed=present,
                details=f"changed={sorted(changed)}",
            )
        )

    for path in scenario.protected_files:
        untouched = path not in changed
        checks.append(
            AcceptanceCheck(
                name=f"protected-file:{path}",
                passed=untouched,
                details="untouched" if untouched else "protected file was modified",
            )
        )

    for relative_path, forbidden_values in scenario.forbidden_substrings.items():
        target = root / relative_path
        content = target.read_text(encoding="utf-8") if target.exists() else ""
        for value in forbidden_values:
            absent = value not in content
            checks.append(
                AcceptanceCheck(
                    name=f"forbidden-pattern:{relative_path}",
                    passed=absent,
                    details=f"pattern absent: {value!r}" if absent else f"found forbidden pattern: {value!r}",
                )
            )

    for index, validation in enumerate(scenario.validation_commands, start=1):
        result = subprocess.run(
            validation.command,
            cwd=root,
            capture_output=True,
            text=True,
        )
        passed = result.returncode == validation.expected_exit
        output = (result.stdout + "\n" + result.stderr).strip()
        if len(output) > 1200:
            output = output[-1200:]
        checks.append(
            AcceptanceCheck(
                name=f"validation-command:{index}",
                passed=passed,
                details=(
                    f"exit={result.returncode}, expected={validation.expected_exit}\n{output}"
                ),
            )
        )

    passed_count = sum(1 for check in checks if check.passed)
    score = 1.0 if not checks else passed_count / len(checks)
    return AcceptanceReport(
        scenario=scenario.name,
        passed=all(check.passed for check in checks),
        score=score,
        checks=checks,
    )
