from __future__ import annotations

import argparse
import json
import os
import py_compile
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STAGES: dict[str, list[str]] = {
    "foundation": [
        "README.md", "docs/architecture.md", "backend/pyproject.toml", "frontend/package.json", "docker-compose.yml"
    ],
    "tenancy-domain": [
        "backend/app/domain/models.py", "backend/app/identity/rbac.py", "backend/app/identity/tenancy.py"
    ],
    "world-state": [
        "backend/app/events/models.py", "backend/app/world_state/models.py", "backend/app/world_state/service.py"
    ],
    "connectors": [
        "backend/app/connectors/base.py", "backend/app/connectors/weather.py", "backend/app/connectors/satellite.py",
        "backend/app/connectors/soil.py", "backend/app/connectors/iot.py", "backend/app/connectors/deere.py",
        "backend/app/connectors/erp.py", "backend/app/connectors/regulatory.py"
    ],
    "intelligence": [
        "backend/app/intelligence/risk.py", "backend/app/intelligence/forecasting.py",
        "backend/app/intelligence/optimization.py", "backend/app/intelligence/model_registry.py"
    ],
    "governance": [
        "backend/app/tools/registry.py", "backend/app/policy/engine.py", "backend/app/approvals/service.py",
        "backend/app/actions/models.py"
    ],
    "agents": [
        "backend/app/agents/contracts.py", "backend/app/agents/supervisor.py",
        "backend/app/agents/conflict_resolver.py", "backend/app/agents/registry.py", "backend/app/agents/blackboard.py"
    ],
    "operations": [
        "backend/app/operations/tasks.py", "backend/app/operations/scheduling.py",
        "backend/app/inventory/service.py", "backend/app/workflows/definitions.py"
    ],
    "business-modules": [
        "backend/app/compliance/engine.py", "backend/app/procurement/service.py",
        "backend/app/logistics/service.py", "backend/app/finance/service.py"
    ],
    "api-platform": [
        "backend/app/main.py", "backend/app/api/farms.py", "backend/app/api/fields.py",
        "backend/app/api/recommendations.py", "backend/app/api/tasks.py", "backend/app/api/agent_runs.py",
        "backend/app/api/actions.py", "backend/app/api/integrations.py", "backend/app/api/webhooks.py"
    ],
    "web-product": [
        "frontend/app/page.tsx", "frontend/app/platform/page.tsx", "frontend/app/solutions/page.tsx",
        "frontend/app/industries/page.tsx", "frontend/app/developers/page.tsx", "frontend/app/resources/page.tsx",
        "frontend/app/security/page.tsx", "frontend/app/pricing/page.tsx", "frontend/app/company/page.tsx",
        "frontend/app/book-demo/page.tsx", "frontend/app/app/command-center/page.tsx", "frontend/app/app/map/page.tsx",
        "frontend/app/app/today/page.tsx", "frontend/app/app/ask/page.tsx", "frontend/app/app/agents/page.tsx",
        "frontend/app/app/alerts/page.tsx", "frontend/app/app/actions/page.tsx", "frontend/app/app/timeline/page.tsx",
        "frontend/app/app/farms/page.tsx", "frontend/app/app/fields/page.tsx"
    ],
    "onboarding-mobile": [
        "backend/app/onboarding/service.py", "backend/app/voice/service.py",
        "frontend/app/app/onboarding/page.tsx", "frontend/app/app/my-tasks/page.tsx", "frontend/public/manifest.json"
    ],
    "security-observability": [
        "backend/app/audit/service.py", "backend/app/security/untrusted_data.py",
        "backend/app/observability/telemetry.py", "backend/app/evaluation/scenarios.py", "docs/security.md"
    ],
    "deployment": [
        "infra/terraform/main.tf", ".github/workflows/ci.yml", "backend/Dockerfile",
        "frontend/Dockerfile", "docs/runbooks/operations.md"
    ],
}

FINAL_EXTRA = [
    "backend/app/main.py", "backend/app/domain/models.py", "backend/app/world_state/service.py",
    "backend/app/policy/engine.py", "backend/app/agents/supervisor.py", "backend/app/compliance/engine.py",
    "frontend/app/page.tsx", "frontend/app/app/command-center/page.tsx", "infra/terraform/main.tf",
    ".github/workflows/ci.yml", "docs/architecture.md", "docs/security.md"
]

FORBIDDEN_GLOBAL = [
    "TODO: implement later", "pass  # TODO", "ALLOW_ALL_TENANTS", "DISABLE_AUTH = True",
    "BYPASS_APPROVAL = True", "IGNORE_COMPLIANCE = True",
]

REQUIRED_MARKERS: dict[str, list[tuple[str, str]]] = {
    "tenancy-domain": [
        ("backend/app/identity/rbac.py", "OWNER"), ("backend/app/identity/rbac.py", "COMPLIANCE"),
        ("backend/app/identity/tenancy.py", "organization_id"), ("backend/app/domain/models.py", "CropCycle"),
        ("backend/app/domain/models.py", "Field"),
    ],
    "world-state": [
        ("backend/app/world_state/models.py", "confidence"), ("backend/app/world_state/models.py", "fresh"),
        ("backend/app/events/models.py", "event_type"), ("backend/app/world_state/service.py", "stale"),
    ],
    "connectors": [
        ("backend/app/connectors/base.py", "capabil"), ("backend/app/connectors/weather.py", "forecast"),
        ("backend/app/connectors/satellite.py", "NDVI"), ("backend/app/connectors/iot.py", "Sensor"),
        ("backend/app/connectors/regulatory.py", "evidence"),
    ],
    "governance": [
        ("backend/app/policy/engine.py", "REQUIRE_APPROVAL"), ("backend/app/policy/engine.py", "DENY"),
        ("backend/app/tools/registry.py", "CRITICAL"), ("backend/app/approvals/service.py", "approval"),
    ],
    "agents": [
        ("backend/app/agents/contracts.py", "evidence"), ("backend/app/agents/supervisor.py", "Supervisor"),
        ("backend/app/agents/conflict_resolver.py", "fresh"), ("backend/app/agents/blackboard.py", "constraint"),
    ],
    "business-modules": [
        ("backend/app/compliance/engine.py", "harvest"), ("backend/app/procurement/service.py", "RFQ"),
        ("backend/app/logistics/service.py", "shipment"),
    ],
    "api-platform": [
        ("backend/app/main.py", "FastAPI"), ("backend/app/api/actions.py", "approve"),
        ("backend/app/api/webhooks.py", "webhook"), ("backend/app/api/agent_runs.py", "agent"),
    ],
    "web-product": [
        ("frontend/app/page.tsx", "agricultur"), ("frontend/app/platform/page.tsx", "World State"),
        ("frontend/app/developers/page.tsx", "API"), ("frontend/app/app/command-center/page.tsx", "Command"),
        ("frontend/app/app/map/page.tsx", "Map"), ("frontend/app/app/today/page.tsx", "Today"),
        ("frontend/app/app/ask/page.tsx", "Ask"), ("frontend/app/app/agents/page.tsx", "Agent"),
        ("frontend/app/app/actions/page.tsx", "Appro"), ("frontend/app/app/timeline/page.tsx", "Timeline"),
    ],
    "security-observability": [
        ("backend/app/security/untrusted_data.py", "untrusted"), ("backend/app/audit/service.py", "audit"),
        ("backend/app/observability/telemetry.py", "trace"), ("backend/app/evaluation/scenarios.py", "stale"),
    ],
}


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def check_files(paths: list[str]) -> None:
    missing = [path for path in paths if not (ROOT / path).is_file()]
    if missing:
        fail("missing files: " + ", ".join(missing))
    empty = [path for path in paths if (ROOT / path).stat().st_size < 40]
    if empty:
        fail("files are empty/trivial: " + ", ".join(empty))


def check_markers(stage: str) -> None:
    for relative, marker in REQUIRED_MARKERS.get(stage, []):
        text = (ROOT / relative).read_text(encoding="utf-8", errors="replace")
        if marker.lower() not in text.lower():
            fail(f"{relative} missing semantic marker {marker!r}")


def check_no_forbidden() -> None:
    for base in [ROOT / "backend", ROOT / "frontend", ROOT / "infra"]:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in FORBIDDEN_GLOBAL:
                if needle in text:
                    fail(f"forbidden placeholder/security bypass {needle!r} in {path.relative_to(ROOT)}")


def check_python_compiles() -> None:
    backend = ROOT / "backend"
    if not backend.exists():
        return
    for path in backend.rglob("*.py"):
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            fail(f"python compile failed for {path.relative_to(ROOT)}: {exc.msg}")


def check_json_files() -> None:
    for relative in ["frontend/package.json", "frontend/public/manifest.json"]:
        path = ROOT / relative
        if path.exists():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                fail(f"invalid JSON in {relative}: {exc}")


def check_enterprise_density() -> None:
    py_files = list((ROOT / "backend").rglob("*.py")) if (ROOT / "backend").exists() else []
    ts_files: list[Path] = []
    if (ROOT / "frontend").exists():
        ts_files = [*list((ROOT / "frontend").rglob("*.ts")), *list((ROOT / "frontend").rglob("*.tsx"))]
    if len(py_files) < 30:
        fail(f"enterprise backend is under-built: only {len(py_files)} Python modules")
    if len(ts_files) < 20:
        fail(f"enterprise frontend is under-built: only {len(ts_files)} TypeScript modules")
    content = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in py_files)
    required_concepts = [
        "organization_id", "farm_id", "evidence", "confidence", "approval", "audit",
        "idempot", "stale", "risk", "event", "world", "connector", "policy"
    ]
    missing = [value for value in required_concepts if value.lower() not in content.lower()]
    if missing:
        fail("enterprise backend lacks cross-cutting concepts: " + ", ".join(missing))


def check_protected_baseline() -> None:
    for name in ["MASTER_PLAN.md", "verify_enterprise.py"]:
        if not (ROOT / name).is_file():
            fail(f"protected benchmark file missing: {name}")


def _wait_http(url: str, *, contains: str | None = None, attempts: int = 30) -> None:
    last_error = ""
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                body = response.read().decode("utf-8", errors="replace")
                if response.status < 400 and (contains is None or contains.lower() in body.lower()):
                    return
                last_error = f"status={response.status} body={body[:200]}"
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(2)
    fail(f"runtime endpoint did not become ready: {url}: {last_error}")


def check_strict_runtime() -> None:
    if os.environ.get("EVERSTATE_ENTERPRISE_STRICT", "0") != "1":
        return
    if shutil.which("docker") is None:
        fail("strict enterprise runtime gate requires Docker")
    compose = ["docker", "compose"]
    config = subprocess.run(compose + ["config", "--quiet"], cwd=ROOT, check=False, capture_output=True, text=True)
    if config.returncode != 0:
        fail("docker compose config failed: " + (config.stderr or config.stdout)[-1200:])
    build = subprocess.run(compose + ["build"], cwd=ROOT, check=False, capture_output=True, text=True, timeout=1800)
    if build.returncode != 0:
        fail("docker compose build failed: " + (build.stderr or build.stdout)[-2000:])
    env = os.environ.copy()
    env.setdefault("AGRI_CONNECTOR_MODE", "mock")
    env.setdefault("AGRI_DISABLE_PHYSICAL_ACTIONS", "1")
    up = subprocess.run(compose + ["up", "-d"], cwd=ROOT, check=False, capture_output=True, text=True, env=env)
    if up.returncode != 0:
        fail("docker compose up failed: " + (up.stderr or up.stdout)[-1600:])
    try:
        _wait_http("http://127.0.0.1:8000/health")
        _wait_http("http://127.0.0.1:3000", contains="agricultur")
    finally:
        subprocess.run(compose + ["down", "-v", "--remove-orphans"], cwd=ROOT, check=False, capture_output=True, text=True)


def run(stage: str) -> None:
    if stage == "final":
        required: list[str] = []
        for values in STAGES.values():
            required.extend(values)
        required.extend(FINAL_EXTRA)
        check_files(sorted(set(required)))
        for name in STAGES:
            check_markers(name)
        check_enterprise_density()
    else:
        if stage not in STAGES:
            fail(f"unknown stage {stage!r}")
        check_files(STAGES[stage])
        check_markers(stage)
    check_no_forbidden()
    check_python_compiles()
    check_json_files()
    check_protected_baseline()
    if stage == "final":
        check_strict_runtime()
    print(f"PASS: enterprise stage {stage}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    args = parser.parse_args()
    run(args.stage)


if __name__ == "__main__":
    main()
