from __future__ import annotations

from pathlib import Path

from everstate.phased_autobuild import AutobuildPlan


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "agri_reliability_v2"


def test_v2_reliability_plan_is_valid_and_gate_order_is_explicit():
    plan = AutobuildPlan.load(BENCHMARK / "plan.json")

    assert plan.name == "EVR-AGRI-RELIABILITY-002"
    assert [stage.id for stage in plan.stages] == [
        "g0-model",
        "g1-observe",
        "g2-detect",
        "g3-explain",
        "g4-resolve",
        "g5-optimize",
        "g6-govern",
        "g7-execute",
        "g8-integrate",
        "g9-learn",
        "g10-pilot",
        "g11-enterprise",
        "g12-autonomy",
    ]
    assert "MASTER_PRODUCT_ENGINEERING_PLAN_V2.md" in plan.protected_files
    assert "verify_reliability.py" in plan.protected_files
    assert "Exception Resolution Success Rate" in " ".join(plan.decisions)


def test_v2_transition_requires_completed_real_enterprise_run():
    runner = (BENCHMARK / "run_after_enterprise.sh").read_text(encoding="utf-8")

    assert 'data.get("passed") is not True' in runner
    assert 'int(s.get("attempts", 0)) < 1' in runner
    assert ".git', '.everstate'" in runner
    assert "MASTER_PRODUCT_ENGINEERING_PLAN_V2.md" in runner
    assert "EVR-AGRI-RELIABILITY-002" in runner


def test_v2_contract_keeps_exception_reliability_as_product_center():
    contract = (BENCHMARK / "template" / "MASTER_PRODUCT_ENGINEERING_PLAN_V2.md").read_text(
        encoding="utf-8"
    )

    assert "Detect Exception" in contract
    assert "No execution success is recorded before verification" in contract
    assert "Exception Resolution Success Rate" in contract
    assert "Canonical Model → Connector SDK → World State → Exception Object" in contract
