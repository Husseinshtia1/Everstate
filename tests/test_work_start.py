from __future__ import annotations

from pathlib import Path

from everstate.continuation_readiness import assess_continuation_readiness
from everstate.service import EverstateService
from everstate.storage import LocalStore
from everstate.work_start import checkpoint_before_provider


def _service(tmp_path: Path) -> EverstateService:
    return EverstateService(LocalStore(tmp_path / "everstate.db"))


def test_checkpoint_persists_task_and_next_action_before_provider(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    service = _service(tmp_path)
    service.set_objective(root, "SHIP_CONTINUITY")

    checkpoint = checkpoint_before_provider(
        service,
        root=root,
        task="RUN_REAL_FAILOVER",
        target="codex",
    )

    state = service.status(root)
    assert state.current_task == "RUN_REAL_FAILOVER"
    assert state.next_action == "Continue current task in codex: RUN_REAL_FAILOVER"
    assert checkpoint.state_version == state.version

    readiness = assess_continuation_readiness(service, root)
    assert readiness.status == "READY"
    assert readiness.provider_capture_count == 0
    assert readiness.semantic_capture_count >= 3
    assert readiness.semantic_zero_loss_proven is False


def test_checkpoint_can_set_objective_and_explicit_next_action(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    service = _service(tmp_path)

    checkpoint = checkpoint_before_provider(
        service,
        root=root,
        objective="OBJECTIVE_FROM_USER",
        task="TASK_FROM_USER",
        next_action="NEXT_FROM_USER",
        target="claude",
    )

    state = service.status(root)
    assert state.objective == "OBJECTIVE_FROM_USER"
    assert state.current_task == "TASK_FROM_USER"
    assert state.next_action == "NEXT_FROM_USER"
    assert checkpoint.target == "claude"
    assert assess_continuation_readiness(service, root).status == "READY"
