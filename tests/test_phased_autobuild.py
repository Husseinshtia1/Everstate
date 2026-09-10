from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from everstate.agent_council import CouncilMode, CouncilResult
from everstate.phased_autobuild import AutobuildPlan, AutobuildStage, run_phased_autobuild
from everstate.service import EverstateService
from everstate.storage import LocalStore


class FakeProvider:
    name = "fake-coder"
    automation_supported = True

    def __init__(self, *, fail_first: bool = False, always_fail: bool = False) -> None:
        self.calls = 0
        self.fail_first = fail_first
        self.always_fail = always_fail

    def automation_preflight(self):
        return True, "fake provider ready"

    def launch_automated(self, root: Path, prompt: str) -> int:
        self.calls += 1
        task = "stage-one" if "stage-one" in prompt else "stage-two"
        if self.always_fail:
            return 1
        if self.fail_first and self.calls == 1:
            return 1
        target = root / ("one.txt" if task == "stage-one" else "two.txt")
        target.write_text(f"completed {task}\n", encoding="utf-8")
        return 0


def _plan(*, max_attempts: int = 2) -> AutobuildPlan:
    return AutobuildPlan(
        name="test-plan",
        objective="Build all stages",
        decisions=["Preserve prior stages"],
        constraints=["Do not edit protected.txt"],
        failed_attempts=["Single-shot execution is insufficient"],
        blockers=["Every stage must pass before advancing"],
        protected_files=["protected.txt"],
        stages=[
            AutobuildStage(
                id="stage-one",
                title="Stage One",
                task="Implement stage-one",
                next_action="Advance to stage-two",
                required_changed_files=["one.txt"],
                max_attempts=max_attempts,
            ),
            AutobuildStage(
                id="stage-two",
                title="Stage Two",
                task="Implement stage-two",
                next_action="Finish",
                required_changed_files=["two.txt"],
                max_attempts=max_attempts,
            ),
        ],
    )


def _template(tmp_path: Path) -> Path:
    template = tmp_path / "template"
    template.mkdir()
    (template / "protected.txt").write_text("immutable\n", encoding="utf-8")
    return template


def _fake_council(packet, question: str) -> CouncilResult:
    return CouncilResult(
        project_id=packet.project_id,
        state_version=packet.state_version,
        question=question,
        mode=CouncilMode.DEBATE,
        opinions=(),
        failures=(),
        consensus="TEST_COUNCIL_APPROVES",
        disagreements=(),
        average_confidence=1.0,
        evidence_coverage=1.0,
        quorum_met=True,
    )


def _patch_council(monkeypatch) -> None:
    def preflight(*, service, root, orchestrator, min_agents):
        return (SimpleNamespace(id="reviewer-a"), SimpleNamespace(id="reviewer-b")), "native", SimpleNamespace()

    def council(*, service, root, question, orchestrator, min_agents, mode, rounds):
        packet = service.continuation_packet(root)
        return _fake_council(packet, question), "native", 2

    monkeypatch.setattr("everstate.phased_autobuild._resolve_council_preflight", preflight)
    monkeypatch.setattr("everstate.phased_autobuild.run_council", council)


def test_phased_autobuild_retries_failed_stage_then_advances(tmp_path: Path, monkeypatch) -> None:
    _patch_council(monkeypatch)
    provider = FakeProvider(fail_first=True)
    service = EverstateService(LocalStore(tmp_path / "state.db"))

    run = run_phased_autobuild(
        service=service,
        template=_template(tmp_path),
        workspace=tmp_path / "workspace",
        plan=_plan(),
        provider=provider,
        orchestrator="native",
    )

    assert run.passed is True
    assert provider.calls == 3
    assert [stage.passed for stage in run.stages] == [True, True]
    assert len(run.stages[0].attempts) == 2
    assert len(run.stages[1].attempts) == 1
    assert (run.artifacts_dir / "01-stage-one" / "attempt-1-report.json").is_file()
    assert (run.artifacts_dir / "summary.json").is_file()


def test_phased_autobuild_stops_after_exhausted_stage(tmp_path: Path, monkeypatch) -> None:
    _patch_council(monkeypatch)
    provider = FakeProvider(always_fail=True)
    service = EverstateService(LocalStore(tmp_path / "state.db"))

    run = run_phased_autobuild(
        service=service,
        template=_template(tmp_path),
        workspace=tmp_path / "workspace",
        plan=_plan(max_attempts=2),
        provider=provider,
        orchestrator="native",
    )

    assert run.passed is False
    assert provider.calls == 2
    assert len(run.stages) == 1
    assert run.stages[0].passed is False
    assert not (run.workspace / "two.txt").exists()


def test_phased_autobuild_dry_run_contacts_no_coding_agent(tmp_path: Path, monkeypatch) -> None:
    _patch_council(monkeypatch)
    provider = FakeProvider()
    service = EverstateService(LocalStore(tmp_path / "state.db"))

    run = run_phased_autobuild(
        service=service,
        template=_template(tmp_path),
        workspace=tmp_path / "workspace",
        plan=_plan(),
        provider=provider,
        orchestrator="native",
        dry_run=True,
    )

    assert run.passed is True
    assert provider.calls == 0
    assert len(run.stages) == 2
    assert all(not stage.attempts for stage in run.stages)
