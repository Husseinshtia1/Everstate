from __future__ import annotations

import ast
import json
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

    with tempfile.TemporaryDirectory(prefix="everstate-pulseboard-") as tmp:
        db = Path(tmp) / "nested" / "state" / "pulseboard.json"
        db_arg = str(db)

        initial = parse_json(run("--db", db_arg, "list", "--json"))
        if initial != []:
            fail(f"new database must start empty, got {initial!r}")

        one = parse_json(run("--db", db_arg, "add", "Ship release", "--priority", "high"))
        assert_task(one, task_id=1, title="Ship release", priority="high", status="open")

        two = parse_json(run("--db", db_arg, "add", "Write notes"))
        assert_task(two, task_id=2, title="Write notes", priority="normal", status="open")

        three = parse_json(run("--db", db_arg, "add", "Clean cache", "--priority", "low"))
        assert_task(three, task_id=3, title="Clean cache", priority="low", status="open")

        opened = parse_json(run("--db", db_arg, "list", "--status", "open", "--json"))
        if [task["id"] for task in opened] != [1, 2, 3]:
            fail(f"open tasks must be sorted by id: {opened!r}")

        completed = parse_json(run("--db", db_arg, "done", "2"))
        assert_task(completed, task_id=2, title="Write notes", priority="normal", status="done")

        done_only = parse_json(run("--db", db_arg, "list", "--status", "done", "--json"))
        if len(done_only) != 1:
            fail(f"done filter returned unexpected tasks: {done_only!r}")
        assert_task(done_only[0], task_id=2, title="Write notes", priority="normal", status="done")

        stats = parse_json(run("--db", db_arg, "stats"))
        expected_stats = {
            "total": 3,
            "open": 2,
            "done": 1,
            "by_priority": {"low": 1, "normal": 1, "high": 1},
        }
        if stats != expected_stats:
            fail(f"stats mismatch: expected {expected_stats!r}, got {stats!r}")

        # Every command above ran in a separate Python process. A fourth add
        # therefore proves that persistence and the monotonic id survive restart.
        four = parse_json(run("--db", db_arg, "add", "Postmortem", "--priority", "high"))
        assert_task(four, task_id=4, title="Postmortem", priority="high", status="open")

        unknown = run("--db", db_arg, "done", "999", expected=2)
        if not unknown.stderr.strip():
            fail("unknown task id must produce a useful stderr message")

        invalid_priority = run(
            "--db", db_arg,
            "add", "Invalid priority",
            "--priority", "urgent",
            expected=2,
        )
        if not invalid_priority.stderr.strip():
            fail("invalid priority must produce a useful stderr message")

        if not db.is_file():
            fail("database file was not created at the requested nested path")
        try:
            json.loads(db.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"persisted database is not valid JSON: {exc}")

    print("EVR-SYSTEM-001 PASS")


if __name__ == "__main__":
    main()
