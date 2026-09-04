from __future__ import annotations

import subprocess
from pathlib import Path

from everstate.acceptance import ContinuityScenario, ValidationCommand, evaluate_scenario, seed_scenario
from everstate.service import EverstateService
from everstate.storage import LocalStore


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def make_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Everstate Test")
    (root / "auth.py").write_text(
        "from urllib.parse import urlparse\n\n"
        "ALLOWED_HOST = 'app.example.com'\n\n"
        "def normalize_redirect(uri: str) -> str:\n"
        "    parsed = urlparse(uri)\n"
        "    if parsed.netloc != ALLOWED_HOST:\n"
        "        raise ValueError('untrusted redirect host')\n"
        "    path = parsed.path or '/'\n"
        "    return f'https://{ALLOWED_HOST}{path}'\n",
        encoding="utf-8",
    )
    (root / "schema.sql").write_text("CREATE TABLE sessions(id TEXT);\n", encoding="utf-8")
    (root / "test_auth.py").write_text(
        "import pytest\n"
        "from auth import normalize_redirect\n\n"
        "def test_query_is_preserved():\n"
        "    assert normalize_redirect('https://app.example.com/cb?code=abc') == 'https://app.example.com/cb?code=abc'\n\n"
        "def test_untrusted_host_is_rejected():\n"
        "    with pytest.raises(ValueError):\n"
        "        normalize_redirect('https://evil.example/cb?code=abc')\n",
        encoding="utf-8",
    )
    git(root, "add", ".")
    git(root, "commit", "-m", "interrupted state")
    return root


def scenario() -> ContinuityScenario:
    return ContinuityScenario(
        name="auth_redirect",
        objective="Fix callback without weakening security",
        current_task="Preserve query string",
        decisions=["Keep trusted-host validation"],
        constraints=["Do not modify schema.sql"],
        failed_attempts=["Removing host validation is rejected"],
        blockers=["Query string is dropped"],
        next_action="Fix auth.py then run tests",
        required_changed_files=["auth.py"],
        protected_files=["schema.sql"],
        forbidden_substrings={"auth.py": ["ALLOW_ANY_REDIRECT = True", "return uri"]},
        validation_commands=[ValidationCommand(command=["python", "-m", "pytest", "-q"])],
    )


def test_acceptance_fails_before_target_agent_changes_project(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    report = evaluate_scenario(root, scenario())

    assert report.passed is False
    assert any(check.name == "required-change:auth.py" and not check.passed for check in report.checks)
    assert any(check.name == "validation-command:1" and not check.passed for check in report.checks)


def test_acceptance_ignores_everstate_and_python_cache_noise(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    (root / ".everstate" / "handoffs").mkdir(parents=True)
    (root / ".everstate" / "handoffs" / "packet.md").write_text("internal\n", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "auth.cpython-312.pyc").write_bytes(b"cache")

    report = evaluate_scenario(root, scenario())
    required = next(check for check in report.checks if check.name == "required-change:auth.py")

    assert required.passed is False
    assert required.details == "changed=[]"


def test_acceptance_passes_after_correct_continuation(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    service = EverstateService(LocalStore(tmp_path / "state.db"))
    prompt = seed_scenario(service, root, scenario())

    assert "Preserve query string" in prompt
    assert "Do not modify schema.sql" in prompt
    assert "Removing host validation is rejected" in prompt

    auth = root / "auth.py"
    auth.write_text(
        "from urllib.parse import urlparse\n\n"
        "ALLOWED_HOST = 'app.example.com'\n\n"
        "def normalize_redirect(uri: str) -> str:\n"
        "    parsed = urlparse(uri)\n"
        "    if parsed.netloc != ALLOWED_HOST:\n"
        "        raise ValueError('untrusted redirect host')\n"
        "    path = parsed.path or '/'\n"
        "    query = f'?{parsed.query}' if parsed.query else ''\n"
        "    return f'https://{ALLOWED_HOST}{path}{query}'\n",
        encoding="utf-8",
    )

    report = evaluate_scenario(root, scenario())

    assert report.passed is True
    assert report.score == 1.0
    assert all(check.passed for check in report.checks)


def test_acceptance_detects_protected_file_violation(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    (root / "schema.sql").write_text("DROP TABLE sessions;\n", encoding="utf-8")

    report = evaluate_scenario(root, scenario())

    protected = next(check for check in report.checks if check.name == "protected-file:schema.sql")
    assert protected.passed is False
