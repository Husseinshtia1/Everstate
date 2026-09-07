from __future__ import annotations

import json
from pathlib import Path

from everstate.capture import CaptureEngine
from everstate.continuation_readiness import assess_continuation_readiness
from everstate.emergency_failover import prepare_emergency_failover
from everstate.service import EverstateService
from everstate.storage import LocalStore


def _engine(tmp_path: Path) -> CaptureEngine:
    return CaptureEngine(EverstateService(LocalStore(tmp_path / "everstate.db")))


def test_readiness_is_partial_when_task_and_next_action_are_missing(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    engine = _engine(tmp_path)
    engine.capture(root=root, kind="objective", value="KEEP_WORKING", source_provider="claude-desktop")
    engine.capture(root=root, kind="constraint", value="NO_LEAKAGE", source_provider="claude-desktop")

    report = assess_continuation_readiness(engine.service, root)

    assert report.status == "PARTIAL"
    assert report.provider_capture_count == 2
    assert report.last_provider_capture_at is not None
    assert report.missing_fields == ("current_task", "next_action")
    assert report.semantic_zero_loss_proven is False


def test_readiness_is_ready_only_with_minimum_handoff_fields_and_provenance(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    engine = _engine(tmp_path)
    engine.capture(root=root, kind="objective", value="OBJECTIVE", source_provider="claude-desktop")
    engine.capture(root=root, kind="task", value="CURRENT_TASK", source_provider="claude-desktop")
    engine.capture(root=root, kind="next_action", value="NEXT_ACTION", source_provider="claude-desktop")

    report = assess_continuation_readiness(engine.service, root)

    assert report.status == "READY"
    assert report.missing_fields == ()
    assert report.provider_capture_count == 3
    assert report.semantic_zero_loss_proven is False


def test_failover_bundle_exposes_partial_readiness_without_blocking_escape(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    engine = _engine(tmp_path)
    engine.capture(root=root, kind="objective", value="OBJECTIVE", source_provider="claude-desktop")

    bundle = prepare_emergency_failover(
        service=engine.service,
        root=root,
        source_provider="claude",
        target_provider="codex",
        output_root=tmp_path / "out",
    )

    payload = json.loads(bundle.json_path.read_text(encoding="utf-8"))
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    markdown = bundle.markdown_path.read_text(encoding="utf-8")

    readiness = payload["continuation_readiness"]
    assert readiness["status"] == "PARTIAL"
    assert readiness["missing_fields"] == ["current_task", "next_action"]
    assert readiness["semantic_zero_loss_proven"] is False
    assert manifest["continuation_readiness"] == "PARTIAL"
    assert manifest["semantic_zero_loss_proven"] is False
    assert "Continuation readiness: PARTIAL" in markdown
    assert "Semantic zero-loss proven: NO" in markdown
    assert "current_task, next_action" in markdown
