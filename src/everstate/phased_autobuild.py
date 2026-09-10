from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from .acceptance import AcceptanceReport, ContinuityScenario, ValidationCommand, evaluate_scenario
from .agent_council import CouncilMode, CouncilResult
from .live_acceptance import (
    _append_checks,
    _council_payload,
    _launch_primary,
    _resolve_council_preflight,
    _write_json,
    prepare_workspace,
    primary_prompt,
    run_council,
)
from .providers import ProviderAdapter
from .service import EverstateService


class AutobuildStage(BaseModel):
    id: str
    title: str
    task: str
    next_action: str
    decisions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    required_changed_files: list[str] = Field(default_factory=list)
    protected_files: list[str] = Field(default_factory=list)
    forbidden_substrings: dict[str, list[str]] = Field(default_factory=dict)
    validation_commands: list[ValidationCommand] = Field(default_factory=list)
    council_question: str | None = None
    max_attempts: int = Field(default=2, ge=1, le=8)

    @model_validator(mode="after")
    def _validate_stage(self) -> "AutobuildStage":
        if not self.id.strip() or not self.title.strip() or not self.task.strip() or not self.next_action.strip():
            raise ValueError("stage id/title/task/next_action must be non-empty")
        if not self.required_changed_files and not self.validation_commands:
            raise ValueError(f"stage {self.id!r} needs an observable required change or validation command")
        return self


class AutobuildPlan(BaseModel):
    name: str
    objective: str
    decisions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    failed_attempts: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    protected_files: list[str] = Field(default_factory=list)
    stages: list[AutobuildStage]

    @model_validator(mode="after")
    def _validate_plan(self) -> "AutobuildPlan":
        if not self.name.strip() or not self.objective.strip():
            raise ValueError("plan name/objective must be non-empty")
        if not self.decisions or not self.constraints or not self.failed_attempts or not self.blockers:
            raise ValueError("enterprise autobuild plans require decisions, constraints, failed_attempts, and blockers")
        if not self.stages:
            raise ValueError("autobuild plan must contain at least one stage")
        ids = [stage.id for stage in self.stages]
        if len(ids) != len(set(ids)):
            raise ValueError("autobuild stage ids must be unique")
        return self

    @classmethod
    def load(cls, path: Path) -> "AutobuildPlan":
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class StageAttempt:
    stage_id: str
    attempt: int
    provider_returncode: int
    report: AcceptanceReport


@dataclass(frozen=True)
class StageRun:
    stage_id: str
    title: str
    passed: bool
    attempts: tuple[StageAttempt, ...]
    council_backend: str
    council_participants: int


@dataclass(frozen=True)
class AutobuildRun:
    workspace: Path
    artifacts_dir: Path
    project_id: str
    provider: str
    passed: bool
    stages: tuple[StageRun, ...]


def _stage_scenario(plan: AutobuildPlan, stage: AutobuildStage) -> ContinuityScenario:
    protected = list(dict.fromkeys([*plan.protected_files, *stage.protected_files]))
    return ContinuityScenario(
        name=f"{plan.name}:{stage.id}",
        objective=plan.objective,
        current_task=stage.task,
        decisions=list(dict.fromkeys([*plan.decisions, *stage.decisions])),
        constraints=list(dict.fromkeys([*plan.constraints, *stage.constraints])),
        failed_attempts=list(plan.failed_attempts),
        blockers=list(plan.blockers),
        next_action=stage.next_action,
        required_changed_files=list(stage.required_changed_files),
        protected_files=protected,
        forbidden_substrings=stage.forbidden_substrings,
        validation_commands=stage.validation_commands,
    )


def _seed_plan(service: EverstateService, root: Path, plan: AutobuildPlan) -> None:
    service.init_project(root)
    service.set_objective(root, plan.objective)
    for value in plan.decisions:
        service.add_decision(root, value)
    for value in plan.constraints:
        service.add_constraint(root, value)
    for value in plan.failed_attempts:
        service.add_failure(root, value)
    for value in plan.blockers:
        service.add_blocker(root, value)
    service.add_constraint(
        root,
        "EVERSTATE_AUTOBUILD: independent council review and acceptance verification are mandatory before every stage completes",
    )


def _activate_stage(service: EverstateService, root: Path, plan: AutobuildPlan, stage: AutobuildStage) -> None:
    service.set_task(root, stage.task)
    service.set_next_action(root, stage.next_action)
    for value in stage.decisions:
        service.add_decision(root, value)
    for value in stage.constraints:
        service.add_constraint(root, value)


def _failure_feedback(report: AcceptanceReport) -> str:
    failed = [check for check in report.checks if not check.passed]
    if not failed:
        return "No failed acceptance checks were reported."
    lines = ["Previous implementation attempt failed these deterministic acceptance checks:"]
    for check in failed:
        lines.append(f"- {check.name}: {check.details}")
    lines.append("Repair the implementation. Do not weaken, delete, or edit protected tests/specifications to make them pass.")
    return "\n".join(lines)


def _stage_prompt(
    *,
    service: EverstateService,
    root: Path,
    scenario: ContinuityScenario,
    council: CouncilResult,
    stage: AutobuildStage,
    attempt: int,
    previous_report: AcceptanceReport | None,
) -> str:
    base = primary_prompt(service=service, root=root, scenario=scenario, council=council)
    feedback = "" if previous_report is None else "\n\n" + _failure_feedback(previous_report)
    return (
        f"AUTOBUILD STAGE {stage.id}: {stage.title}\n"
        f"Attempt: {attempt}/{stage.max_attempts}\n"
        "Work only on the current stage while preserving all already-passing capabilities from earlier stages.\n\n"
        + base
        + feedback
    )


def run_phased_autobuild(
    *,
    service: EverstateService,
    template: Path,
    workspace: Path,
    plan: AutobuildPlan,
    provider: ProviderAdapter,
    orchestrator: str = "ruflo",
    min_council_agents: int = 2,
    dry_run: bool = False,
) -> AutobuildRun:
    if not getattr(provider, "automation_supported", False):
        raise RuntimeError(f"{provider.name} has no verified headless automation contract")
    ready, detail = provider.automation_preflight()
    if not ready:
        raise RuntimeError(f"Primary coding provider {provider.name} is not ready: {detail}")

    root = prepare_workspace(template, workspace)
    _seed_plan(service, root, plan)
    artifacts = root / ".everstate" / "autobuild" / plan.name
    stage_runs: list[StageRun] = []

    for index, stage in enumerate(plan.stages, start=1):
        _activate_stage(service, root, plan, stage)
        scenario = _stage_scenario(plan, stage)
        before_council = service.continuation_packet(root)
        participants, backend, ruflo = _resolve_council_preflight(
            service=service,
            root=root,
            orchestrator=orchestrator,
            min_agents=min_council_agents,
        )
        stage_dir = artifacts / f"{index:02d}-{stage.id}"
        _write_json(
            stage_dir / "preflight.json",
            {
                "stage": stage.model_dump(mode="json"),
                "project_id": before_council.project_id,
                "state_version": before_council.state_version,
                "provider": provider.name,
                "provider_preflight": detail,
                "council_backend": backend,
                "participants": [participant.id for participant in participants],
            },
        )

        if dry_run:
            stage_runs.append(
                StageRun(
                    stage_id=stage.id,
                    title=stage.title,
                    passed=True,
                    attempts=(),
                    council_backend=backend,
                    council_participants=len(participants),
                )
            )
            continue

        question = stage.council_question or (
            f"Review enterprise autobuild stage {stage.id} ({stage.title}) before implementation. "
            "Identify architecture, security, data integrity, tenant isolation, evidence, operability, and regression risks."
        )
        council, backend, participant_count = run_council(
            service=service,
            root=root,
            question=question,
            orchestrator=orchestrator,
            min_agents=min_council_agents,
            mode=CouncilMode.DEBATE,
            rounds=2,
        )
        _write_json(stage_dir / "council.json", _council_payload(council))

        attempts: list[StageAttempt] = []
        previous_report: AcceptanceReport | None = None
        stage_passed = False
        for attempt_number in range(1, stage.max_attempts + 1):
            before = service.continuation_packet(root)
            prompt = _stage_prompt(
                service=service,
                root=root,
                scenario=scenario,
                council=council,
                stage=stage,
                attempt=attempt_number,
                previous_report=previous_report,
            )
            (stage_dir / f"attempt-{attempt_number}-prompt.txt").write_text(prompt, encoding="utf-8")
            returncode = _launch_primary(provider, root, prompt)
            after = service.continuation_packet(root)
            report = evaluate_scenario(root, scenario)
            report = _append_checks(report, provider_returncode=returncode, before=before, after=after)
            _write_json(stage_dir / f"attempt-{attempt_number}-report.json", report.model_dump(mode="json"))
            attempts.append(
                StageAttempt(
                    stage_id=stage.id,
                    attempt=attempt_number,
                    provider_returncode=returncode,
                    report=report,
                )
            )
            if report.passed:
                stage_passed = True
                break
            previous_report = report

        stage_runs.append(
            StageRun(
                stage_id=stage.id,
                title=stage.title,
                passed=stage_passed,
                attempts=tuple(attempts),
                council_backend=backend,
                council_participants=participant_count,
            )
        )
        if not stage_passed:
            break

    passed = len(stage_runs) == len(plan.stages) and all(stage.passed for stage in stage_runs)
    summary = {
        "plan": plan.name,
        "project_id": service.continuation_packet(root).project_id,
        "provider": provider.name,
        "passed": passed,
        "stages": [
            {
                "id": item.stage_id,
                "title": item.title,
                "passed": item.passed,
                "attempts": len(item.attempts),
                "council_backend": item.council_backend,
                "council_participants": item.council_participants,
            }
            for item in stage_runs
        ],
    }
    _write_json(artifacts / "summary.json", summary)
    packet = service.continuation_packet(root)
    return AutobuildRun(
        workspace=root,
        artifacts_dir=artifacts,
        project_id=packet.project_id,
        provider=provider.name,
        passed=passed,
        stages=tuple(stage_runs),
    )
