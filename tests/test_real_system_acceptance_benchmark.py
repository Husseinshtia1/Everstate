from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from everstate.acceptance import ContinuityScenario


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "system_v1" / "pulseboard_autobuild"
TEMPLATE = BENCHMARK / "project"

REFERENCE_APP = r'''from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path


def load_db(path: Path) -> dict:
    if not path.exists():
        return {"next_id": 1, "tasks": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("next_id", 1)
    data.setdefault("tasks", [])
    return data


def save_db(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def emit(task: dict) -> None:
    print(json.dumps(task, separators=(",", ":")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add")
    add.add_argument("title")
    add.add_argument("--priority", choices=("low", "normal", "high"), default="normal")

    listing = sub.add_parser("list")
    listing.add_argument("--status", choices=("open", "done"))
    listing.add_argument("--json", action="store_true")

    done = sub.add_parser("done")
    done.add_argument("id", type=int)

    sub.add_parser("stats")
    args = parser.parse_args()
    path = Path(args.db)
    data = load_db(path)

    if args.command == "add":
        task = {"id": data["next_id"], "title": args.title, "priority": args.priority, "status": "open"}
        data["next_id"] += 1
        data["tasks"].append(task)
        save_db(path, data)
        emit(task)
        return 0

    if args.command == "list":
        tasks = sorted(data["tasks"], key=lambda item: item["id"])
        if args.status:
            tasks = [task for task in tasks if task["status"] == args.status]
        if args.json:
            print(json.dumps(tasks))
        else:
            for task in tasks:
                print(f"{task['id']} {task['status']} {task['priority']} {task['title']}")
        return 0

    if args.command == "done":
        task = next((item for item in data["tasks"] if item["id"] == args.id), None)
        if task is None:
            parser.exit(2, f"unknown task id: {args.id}\n")
        task["status"] = "done"
        save_db(path, data)
        emit(task)
        return 0

    priorities = {"low": 0, "normal": 0, "high": 0}
    for task in data["tasks"]:
        priorities[task["priority"]] += 1
    total = len(data["tasks"])
    done_count = sum(task["status"] == "done" for task in data["tasks"])
    print(json.dumps({"total": total, "open": total - done_count, "done": done_count, "by_priority": priorities}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _workspace(tmp_path: Path) -> Path:
    shutil.copy(TEMPLATE / "verify.py", tmp_path / "verify.py")
    shutil.copy(TEMPLATE / "SPEC.md", tmp_path / "SPEC.md")
    (tmp_path / "pulseboard.py").write_text(REFERENCE_APP, encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "Pulseboard is local JSON task storage. Usage: add, list, done, stats.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_real_system_scenario_loads() -> None:
    scenario = ContinuityScenario.load(BENCHMARK / "scenario.json")
    assert scenario.name == "pulseboard_autobuild_full_system"
    assert "pulseboard.py" in scenario.required_changed_files
    assert {"SPEC.md", "verify.py"} <= set(scenario.protected_files)
    assert scenario.failed_attempts
    assert scenario.blockers


def test_real_system_verifier_accepts_known_good_reference(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    result = subprocess.run(
        [sys.executable, "verify.py"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "EVR-SYSTEM-001 PASS" in result.stdout


def test_real_system_verifier_rejects_missing_application(tmp_path: Path) -> None:
    shutil.copy(TEMPLATE / "verify.py", tmp_path / "verify.py")
    result = subprocess.run(
        [sys.executable, "verify.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "pulseboard.py was not created" in result.stderr
