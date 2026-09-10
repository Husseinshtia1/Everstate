from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from everstate.acceptance import ContinuityScenario
from everstate.live_acceptance import StateLevel, run_real_acceptance
from everstate.service import EverstateService
from everstate.storage import LocalStore


SOLUTION = '''from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def storage_path() -> Path:
    return Path(os.environ.get("TASKBOARD_FILE", ".taskboard.json"))


def load_tasks() -> list[dict[str, object]]:
    path = storage_path()
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("task store must contain a list")
    return data


def save_tasks(tasks: list[dict[str, object]]) -> None:
    path = storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    tmp.replace(path)


def add_task(title: str) -> int:
    title = title.strip()
    if not title:
        raise ValueError("title must not be empty")
    tasks = load_tasks()
    next_id = max((int(item["id"]) for item in tasks), default=0) + 1
    tasks.append({"id": next_id, "title": title, "done": False})
    save_tasks(tasks)
    return next_id


def mark_done(task_id: int) -> bool:
    tasks = load_tasks()
    for item in tasks:
        if int(item["id"]) == task_id:
            item["done"] = True
            save_tasks(tasks)
            return True
    return False


def render_tasks() -> str:
    return "\\n".join(
        f"[{'x' if item['done'] else ' '}] {item['id']} {item['title']}" for item in load_tasks()
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or [])
    if not argv:
        print("usage: taskboard.py add TITLE | list | done ID", file=sys.stderr)
        return 2
    command = argv[0]
    try:
        if command == "add" and len(argv) == 2:
            print(add_task(argv[1]))
            return 0
        if command == "list" and len(argv) == 1:
            output = render_tasks()
            if output:
                print(output)
            return 0
        if command == "done" and len(argv) == 2:
            try:
                task_id = int(argv[1])
            except ValueError:
                print("task id must be an integer", file=sys.stderr)
                return 2
            if not mark_done(task_id):
                print("task not found", file=sys.stderr)
                return 2
            return 0
    except (ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("invalid command", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


class FakeProvider:
    name = "Deterministic Coding Agent"

    def __init__(self) -> None:
        self.calls = 0
        self.prompt = ""

    def launch(self, root: Path, prompt: str) -> int:
        self.calls += 1
        self.prompt = prompt
        (root / "taskboard.py").write_text(SOLUTION, encoding="utf-8")
        return 0


class ExplodingProvider:
    name = "Must Not Run"

    def launch(self, root: Path, prompt: str) -> int:  # pragma: no cover - should never execute
        raise AssertionError("dry-run contacted the primary provider")


class FakeRuflo:
    def health(self):
        return SimpleNamespace(ready=True, version="3.41.1", detail="fake preflight")


def _scenario(repo_root: Path) -> ContinuityScenario:
    return ContinuityScenario.load(repo_root / "benchmarks/real_build_v1/taskboard_cli/scenario.json")


def _template(repo_root: Path) -> Path:
    return repo_root / "benchmarks/real_build_v1/taskboard_cli/project"


def _service(tmp_path: Path) -> EverstateService:
    return EverstateService(LocalStore(tmp_path / "everstate.db"))


def test_real_acceptance_deterministic_primary_agent_passes(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    provider = FakeProvider()
    run = run_real_acceptance(
        service=_service(tmp_path),
        template=_template(repo_root),
        workspace=tmp_path / "workspace",
        scenario=_scenario(repo_root),
        provider=provider,
        state_level=StateLevel.FULL,
        require_council=False,
    )

    assert run.report.passed
    assert run.report.score == 1.0
    assert provider.calls == 1
    assert "CANONICAL EVERSTATE PACKET" in provider.prompt
    assert "Do not modify acceptance_test.py" in provider.prompt
    assert run.final_state_version >= run.initial_state_version
    checks = {check.name: check for check in run.report.checks}
    assert checks["canonical-project-identity"].passed
    assert checks["canonical-semantic-state-preserved"].passed
    assert checks["state-version-monotonic"].passed
    assert (run.workspace / "POLICY.md").read_text(encoding="utf-8").startswith("# Protected acceptance policy")
    assert (run.artifacts_dir / "state-before.json").exists()
    assert (run.artifacts_dir / "acceptance-report.json").exists()


def test_real_acceptance_dry_run_is_preflight_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    calls = {"preflight": 0, "council": 0}

    def fake_preflight(**kwargs):
        calls["preflight"] += 1
        return (SimpleNamespace(id="architect"), SimpleNamespace(id="verifier")), "ruflo", FakeRuflo()

    def fail_council(**kwargs):
        calls["council"] += 1
        raise AssertionError("dry-run executed council models")

    monkeypatch.setattr("everstate.live_acceptance._resolve_council_preflight", fake_preflight)
    monkeypatch.setattr("everstate.live_acceptance.run_council", fail_council)
    run = run_real_acceptance(
        service=_service(tmp_path),
        template=_template(repo_root),
        workspace=tmp_path / "dry-workspace",
        scenario=_scenario(repo_root),
        provider=ExplodingProvider(),
        state_level=StateLevel.CRITICAL,
        require_council=True,
        dry_run=True,
    )

    assert calls == {"preflight": 1, "council": 0}
    assert run.council_backend == "ruflo"
    assert run.council_participants == 2
    assert run.provider_returncode is None
    assert run.report.passed
    assert (run.artifacts_dir / "primary-prompt-preview.txt").exists()


def test_critical_state_level_cannot_disable_council(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "must-not-be-created"
    with pytest.raises(ValueError, match="critical state level requires independent council review"):
        run_real_acceptance(
            service=_service(tmp_path),
            template=_template(repo_root),
            workspace=workspace,
            scenario=_scenario(repo_root),
            provider=FakeProvider(),
            state_level=StateLevel.CRITICAL,
            require_council=False,
        )
    assert not workspace.exists()


def test_ruflo_runtime_artifacts_are_not_project_changes(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    provider = FakeProvider()
    run = run_real_acceptance(
        service=_service(tmp_path),
        template=_template(repo_root),
        workspace=tmp_path / "artifact-workspace",
        scenario=_scenario(repo_root),
        provider=provider,
        require_council=False,
    )
    (run.workspace / ".claude-flow").mkdir()
    (run.workspace / ".claude-flow" / "runtime.json").write_text("{}", encoding="utf-8")

    from everstate.acceptance import evaluate_scenario

    report = evaluate_scenario(run.workspace, _scenario(repo_root))
    assert report.passed
