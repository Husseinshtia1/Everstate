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


def _git_changed_files(root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    changed: set[str] = set()
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        changed.add(path)
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


def evaluate_scenario(root: Path, scenario: ContinuityScenario) -> AcceptanceReport:
    root = root.resolve()
    changed = _git_changed_files(root)
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
