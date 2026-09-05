from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import everstate.try_cli as try_cli
from everstate.models import ProjectState
from everstate.storage import LocalStore
from everstate.test_transfer import create_test_transfer_bundle
from everstate.transfer_plan import RegisteredProject, SourceEnvironment
from everstate.try_cli import app

runner = CliRunner()


def _seed_store(tmp_path: Path) -> tuple[LocalStore, RegisteredProject]:
    store = LocalStore(tmp_path / "everstate.db")
    root = tmp_path / "project"
    root.mkdir()
    project = RegisteredProject("proj_test", "Test Project", root)
    store.upsert_project(project.project_id, project.name, project.root_path)
    store.save_state(
        ProjectState(
            project_id=project.project_id,
            version=7,
            objective="Continue safely",
            current_task="Test transfer",
            active_constraints=["Do not mutate source"],
            decisions=["Use verified state"],
            failed_attempts=["Blind transcript copy"],
            blockers=[],
            modified_files=[],
            next_action="Create isolated bundle",
            unresolved_conflicts=[],
        )
    )
    return store, project


def test_bundle_does_not_mutate_canonical_state(tmp_path: Path) -> None:
    store, project = _seed_store(tmp_path)
    before = store.latest_state(project.project_id)
    assert before is not None

    bundle = create_test_transfer_bundle(
        store,
        project=project,
        source=SourceEnvironment.CODEX,
        destination="gemini",
        session_id="session-123",
        output_root=tmp_path / "bundles",
    )

    after = store.latest_state(project.project_id)
    assert after is not None
    assert after.version == before.version == 7
    assert bundle.state_version == 7
    assert bundle.directory.parent == (tmp_path / "bundles").resolve()

    metadata = json.loads(bundle.metadata_path.read_text(encoding="utf-8"))
    assert metadata["mode"] == "TEST_ONLY"
    assert metadata["provider_launched"] is False
    assert metadata["canonical_state_mutated"] is False
    assert metadata["source_session"] == "session-123"
    assert metadata["state_version"] == 7
    assert "EVERSTATE CONTINUATION PACKET" in bundle.markdown_path.read_text(encoding="utf-8")


def test_bundle_requires_existing_canonical_state(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "everstate.db")
    root = tmp_path / "project"
    root.mkdir()
    project = RegisteredProject("proj_empty", "Empty", root)
    store.upsert_project(project.project_id, project.name, project.root_path)

    try:
        create_test_transfer_bundle(
            store,
            project=project,
            source=SourceEnvironment.CURRENT_WORKTREE,
            destination="manual",
            output_root=tmp_path / "bundles",
        )
    except ValueError as exc:
        assert "has no canonical Everstate state" in str(exc)
    else:
        raise AssertionError("Expected missing-state failure")


def test_everstate_try_creates_bundle_without_launch(monkeypatch, tmp_path: Path) -> None:
    store, _ = _seed_store(tmp_path)
    monkeypatch.setattr(try_cli, "_store", lambda: store)

    output_root = tmp_path / "try-output"
    result = runner.invoke(
        app,
        [
            "--from",
            "current-worktree",
            "--project",
            "proj_test",
            "--to",
            "gemini",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0
    assert "TEST_TRANSFER_READY" in result.stdout
    assert "No provider was launched" in result.stdout
    assert store.latest_state("proj_test").version == 7
    assert any(path.name == "transfer-review.json" for path in output_root.rglob("transfer-review.json"))
