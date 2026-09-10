from __future__ import annotations

import ast
import json
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "pulseboard.py"
README = ROOT / "README.md"


def fail(message: str) -> None:
    raise AssertionError(message)


def run(*args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(APP), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != expected:
        fail(
            f"command {args!r} exited {result.returncode}, expected {expected}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def parse_json(result: subprocess.CompletedProcess[str]):
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        fail(f"stdout was not valid JSON: {result.stdout!r}; {exc}")


def assert_task(value, *, task_id: int, title: str, priority: str, status: str) -> None:
    expected = {"id": task_id, "title": title, "priority": priority, "status": status}
    if value != expected:
        fail(f"task mismatch: expected {expected!r}, got {value!r}")


def verify_import_boundary() -> None:
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(APP))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])

    forbidden_network = {"socket", "urllib", "http", "requests", "aiohttp", "httpx"}
    network_hits = sorted(imported & forbidden_network)
    if network_hits:
        fail(f"network imports are forbidden: {network_hits}")

    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    local_modules = {path.stem for path in ROOT.glob("*.py")}
    non_stdlib = sorted(name for name in imported if name not in stdlib and name not in local_modules)
    if non_stdlib:
        fail(f"third-party imports are forbidden: {non_stdlib}")

    if "os.replace" not in source and ".replace(" not in source:
        fail("implementation does not appear to use an atomic replace operation")


def main() -> None:
    if not APP.is_file():
        fail("pulseboard.py was not created")
    if not README.is_file():
        fail("README.md was not created")

    verify_import_boundary()

    readme_text = README.read_text(encoding="utf-8").lower()
    for term in ("add", "list", "done", "stats", "json", "local"):
        if term not in readme_text:
            fail(f"README.md is missing required usage/documentation term: {term!r}")

    # Runtime-generated values make a static verifier-output implementation fail.
    # Every CLI invocation below is a separate Python process, so successful
    # results also demonstrate persistence across process boundaries.
    titles = [f"task-{secrets.token_hex(6)}" for _ in range(5)]
    priorities = [secrets.choice(("low", "normal", "high")) for _ in titles]

    with tempfile.TemporaryDirectory(prefix="everstate-pulseboard-") as tmp:
        db = Path(tmp) / "nested" / "state" / "pulseboard.json"
        db_arg = str(db)

        initial = parse_json(run("--db", db_arg, "list", "--json"))
        if initial != []:
            fail(f"new database must start empty, got {initial!r}")

        expected_tasks: list[dict[str, object]] = []
        for index, (title, priority) in enumerate(zip(titles, priorities), start=1):
            created = parse_json(run("--db", db_arg, "add", title, "--priority", priority))
            assert_task(created, task_id=index, title=title, priority=priority, status="open")
            expected_tasks.append(created)

        opened = parse_json(run("--db", db_arg, "list", "--status", "open", "--json"))
        if opened != expected_tasks:
            fail(f"open tasks must preserve runtime values and ascending ids: {opened!r}")

        done_id = 2 + secrets.randbelow(3)
        completed = parse_json(run("--db", db_arg, "done", str(done_id)))
        expected_done = dict(expected_tasks[done_id - 1])
        expected_done["status"] = "done"
        if completed != expected_done:
            fail(f"completed task mismatch: expected {expected_done!r}, got {completed!r}")
        expected_tasks[done_id - 1] = expected_done

        done_only = parse_json(run("--db", db_arg, "list", "--status", "done", "--json"))
        if done_only != [expected_done]:
            fail(f"done filter returned unexpected tasks: {done_only!r}")

        open_expected = [task for task in expected_tasks if task["status"] == "open"]
        open_only = parse_json(run("--db", db_arg, "list", "--status", "open", "--json"))
        if open_only != open_expected:
            fail(f"open filter returned unexpected tasks: {open_only!r}")

        priority_counts = {"low": 0, "normal": 0, "high": 0}
        for task in expected_tasks:
            priority_counts[str(task["priority"])] += 1
        expected_stats = {
            "total": len(expected_tasks),
            "open": len(open_expected),
            "done": 1,
            "by_priority": priority_counts,
        }
        stats = parse_json(run("--db", db_arg, "stats"))
        if stats != expected_stats:
            fail(f"stats mismatch: expected {expected_stats!r}, got {stats!r}")

        # A later create proves IDs remain monotonic after completion and restart.
        final_title = f"post-{secrets.token_hex(6)}"
        final_priority = secrets.choice(("low", "normal", "high"))
        final_task = parse_json(
            run("--db", db_arg, "add", final_title, "--priority", final_priority)
        )
        assert_task(
            final_task,
            task_id=len(expected_tasks) + 1,
            title=final_title,
            priority=final_priority,
            status="open",
        )

        if not db.is_file():
            fail("database file was not created at the requested nested path")
        before_invalid = db.read_bytes()

        unknown = run("--db", db_arg, "done", "999999999", expected=2)
        if not unknown.stderr.strip():
            fail("unknown task id must produce a useful stderr message")
        if db.read_bytes() != before_invalid:
            fail("unknown task id corrupted or rewrote persisted task data")

        invalid_priority = run(
            "--db", db_arg,
            "add", f"invalid-{secrets.token_hex(4)}",
            "--priority", "urgent",
            expected=2,
        )
        if not invalid_priority.stderr.strip():
            fail("invalid priority must produce a useful stderr message")
        if db.read_bytes() != before_invalid:
            fail("invalid priority corrupted or rewrote persisted task data")

        try:
            persisted = json.loads(db.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"persisted database is not valid JSON: {exc}")
        if not isinstance(persisted, dict) or "tasks" not in persisted:
            fail("persisted database does not contain durable task state")

    print("EVR-SYSTEM-001 PASS")


if __name__ == "__main__":
    main()
