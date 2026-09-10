from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parent
SCRIPT = ROOT / "taskboard.py"


class TaskboardAcceptance(unittest.TestCase):
    def run_cli(self, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_full_user_flow_and_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "tasks.json"
            env = os.environ.copy()
            env["TASKBOARD_FILE"] = str(store)

            first = self.run_cli("add", "Ship release", env=env)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("1", first.stdout)

            second = self.run_cli("add", "Write migration notes", env=env)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("2", second.stdout)

            listing = self.run_cli("list", env=env)
            self.assertEqual(listing.returncode, 0, listing.stderr)
            self.assertEqual(
                listing.stdout.strip().splitlines(),
                ["[ ] 1 Ship release", "[ ] 2 Write migration notes"],
            )

            done = self.run_cli("done", "1", env=env)
            self.assertEqual(done.returncode, 0, done.stderr)

            listing2 = self.run_cli("list", env=env)
            self.assertEqual(listing2.returncode, 0, listing2.stderr)
            self.assertEqual(
                listing2.stdout.strip().splitlines(),
                ["[x] 1 Ship release", "[ ] 2 Write migration notes"],
            )

            persisted = json.loads(store.read_text(encoding="utf-8"))
            self.assertEqual(
                persisted,
                [
                    {"id": 1, "title": "Ship release", "done": True},
                    {"id": 2, "title": "Write migration notes", "done": False},
                ],
            )

    def test_invalid_inputs_do_not_corrupt_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "tasks.json"
            env = os.environ.copy()
            env["TASKBOARD_FILE"] = str(store)

            blank = self.run_cli("add", "   ", env=env)
            self.assertNotEqual(blank.returncode, 0)

            add = self.run_cli("add", "Keep me", env=env)
            self.assertEqual(add.returncode, 0, add.stderr)
            before = store.read_text(encoding="utf-8")

            missing = self.run_cli("done", "999", env=env)
            self.assertEqual(missing.returncode, 2)
            self.assertEqual(store.read_text(encoding="utf-8"), before)

            bad_id = self.run_cli("done", "not-a-number", env=env)
            self.assertNotEqual(bad_id.returncode, 0)
            self.assertEqual(store.read_text(encoding="utf-8"), before)

    def test_ids_continue_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "tasks.json"
            env = os.environ.copy()
            env["TASKBOARD_FILE"] = str(store)

            self.assertEqual(self.run_cli("add", "One", env=env).returncode, 0)
            self.assertEqual(self.run_cli("add", "Two", env=env).returncode, 0)
            third = self.run_cli("add", "Three", env=env)
            self.assertEqual(third.returncode, 0, third.stderr)
            data = json.loads(store.read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in data], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
