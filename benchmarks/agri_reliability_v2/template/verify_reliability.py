from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STAGE_FILES: dict[str, list[str]] = {
    "g0-model": [
        "backend/app/domain/models.py",
        "backend/app/identity/entity_resolution.py",
        "backend/app/identity/identity_graph.py",
    ],
    "g1-observe": [
        "backend/app/connectors/base.py",
        "backend/app/connectors/registry.py",
        "backend/app/world_state/service.py",
        "backend/app/world_state/freshness.py",
        "backend/app/provenance/service.py",
    ],
    "g2-detect": [
        "backend/app/events/models.py",
        "backend/app/exceptions/models.py",
        "backend/app/exceptions/service.py",
        "backend/app/dependencies/service.py",
        "backend/app/impact/service.py",
    ],
    "g3-explain": [
        "backend/app/evidence/service.py",
        "backend/app/evidence/confidence.py",
        "backend/app/models/gateway.py",
        "backend/app/security/untrusted_data.py",
    ],
    "g4-resolve": [
        "backend/app/agents/supervisor.py",
        "backend/app/agents/contracts.py",
        "backend/app/agents/registry.py",
        "backend/app/agents/blackboard.py",
        "backend/app/agents/identity.py",
    ],
    "g5-optimize": [
        "backend/app/intelligence/optimization.py",
        "backend/app/plans/models.py",
        "backend/app/plans/service.py",
        "backend/app/finance/scoring.py",
    ],
    "g6-govern": [
        "backend/app/policy/engine.py",
        "backend/app/approvals/service.py",
        "backend/app/data_vault/service.py",
        "backend/app/actions/models.py",
        "backend/app/tools/registry.py",
    ],
    "g7-execute": [
        "backend/app/workflows/definitions.py",
        "backend/app/actions/executor.py",
        "backend/app/actions/idempotency.py",
        "backend/app/actions/verification.py",
    ],
    "g8-integrate": [
        "backend/app/connectors/mqtt.py",
        "backend/app/connectors/deere.py",
        "backend/app/connectors/odoo.py",
        "backend/app/connectors/agronomy.py",
        "backend/app/connectors/messaging.py",
    ],
    "g9-learn": [
        "backend/app/outcomes/models.py",
        "backend/app/outcomes/service.py",
        "backend/app/roi/ledger.py",
        "backend/app/intelligence/model_registry.py",
    ],
    "g10-pilot": [
        "frontend/app/app/attention/page.tsx",
        "frontend/app/app/exceptions/[id]/page.tsx",
        "backend/app/demo/weather_exception.py",
        "backend/app/evaluation/scenarios.py",
    ],
    "g11-enterprise": [
        "backend/app/evaluation/release_blockers.py",
        "backend/app/observability/telemetry.py",
        "docs/runbooks/operations.md",
        "docs/security.md",
    ],
    "g12-autonomy": [
        "backend/app/autonomy/contracts.py",
        "backend/app/autonomy/controller.py",
        "backend/app/evaluation/autonomy.py",
    ],
}

SEMANTIC_MARKERS: dict[str, list[str]] = {
    "g0-model": ["exception", "outcome", "confidence", "alias"],
    "g1-observe": ["fresh", "stale", "provenance", "capabil"],
    "g2-detect": ["exception", "impact", "severity", "depend"],
    "g3-explain": ["evidence", "unknown", "confidence", "stale"],
    "g4-resolve": ["supervisor", "constraint", "evidence", "scope"],
    "g5-optimize": ["feasib", "risk", "cost", "constraint"],
    "g6-govern": ["allow", "deny", "approval", "audit"],
    "g7-execute": ["idempot", "verif", "revers", "compens"],
    "g8-integrate": ["health", "capabil", "mock", "retry"],
    "g9-learn": ["expected", "observed", "verified", "attributed"],
    "g10-pilot": ["exception", "plan", "approve", "outcome"],
    "g11-enterprise": ["tenant", "unauthorized", "duplicate", "audit"],
    "g12-autonomy": ["policy", "override", "verification", "risk"],
}

FORBIDDEN = ("TODO", "FIXME", "pass #", "NotImplementedError")


def check_stage(stage: str) -> list[str]:
    failures: list[str] = []
    required = STAGE_FILES[stage]
    combined = ""
    for rel in required:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing required file: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if len(text.strip()) < 80:
            failures.append(f"file is too small to be substantive: {rel}")
        for marker in FORBIDDEN:
            if marker in text:
                failures.append(f"placeholder marker {marker!r} in {rel}")
        combined += "\n" + text.lower()

    for marker in SEMANTIC_MARKERS[stage]:
        if marker.lower() not in combined:
            failures.append(f"stage semantics missing marker: {marker}")

    protected = ROOT / "MASTER_PRODUCT_ENGINEERING_PLAN_V2.md"
    if not protected.is_file() or "Make complex agricultural operations continue correctly" not in protected.read_text(encoding="utf-8"):
        failures.append("protected v2 master plan missing or changed")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=list(STAGE_FILES))
    args = parser.parse_args()
    failures = check_stage(args.stage)
    if failures:
        print(f"FAIL {args.stage}")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"PASS {args.stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
