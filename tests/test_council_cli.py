from __future__ import annotations

from everstate.continuity import ContinuationPacket
from everstate.council_cli import _council_model_order, _select_participants
from everstate.provider_fabric import FabricHealth, FabricTarget


class FakeFabric:
    def __init__(self, name: str):
        self.name = name


def test_no_cloud_constraint_excludes_all_remote_council_fabrics(monkeypatch):
    seen: list[str] = []

    def fake_safe(name, factory):
        seen.append(name)
        fabric = FakeFabric(name)
        return fabric, FabricHealth("READY", True, "test"), (FabricTarget(id=f"{name}-model"),)

    monkeypatch.setattr("everstate.council_cli._safe_fabric", fake_safe)
    packet = ContinuationPacket(project_id="proj_local", state_version=3, constraints=["NO_CLOUD"])

    participants, health, local_only = _select_participants(
        packet,
        ("architect", "critic", "verifier"),
        3,
    )

    assert local_only is True
    assert seen == ["ypipe"]
    assert {participant.fabric.name for participant in participants} == {"ypipe"}
    assert health["freellmapi"]["status"] == "FORBIDDEN"
    assert health["omniroute"]["status"] == "FORBIDDEN"


def test_cloud_allowed_can_use_multiple_fabrics(monkeypatch):
    def fake_safe(name, factory):
        fabric = FakeFabric(name)
        return fabric, FabricHealth("READY", True, "test"), (FabricTarget(id=f"{name}-model"),)

    monkeypatch.setattr("everstate.council_cli._safe_fabric", fake_safe)
    packet = ContinuationPacket(project_id="proj_cloud", state_version=4)

    participants, _, local_only = _select_participants(
        packet,
        ("architect", "critic", "verifier"),
        3,
    )

    assert local_only is False
    assert [participant.fabric.name for participant in participants] == ["ypipe", "freellmapi", "omniroute"]


def test_freellmapi_council_prefers_callable_direct_models_over_group_aliases():
    models = (
        "auto",
        "allam-2-7b",
        "aya-expanse-32b",
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gpt-oss-120b",
        "gpt-oss-safeguard-20b",
    )

    ranked = _council_model_order("freellmapi", models)

    assert ranked[:3] == (
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gpt-oss-120b",
    )
    assert ranked.index("claude-sonnet-4-5") > 2
    assert ranked.index("auto") > 2


def test_select_participants_uses_callable_ranked_freellmapi_targets_when_only_remote_ready(monkeypatch):
    def fake_safe(name, factory):
        if name == "freellmapi":
            fabric = FakeFabric(name)
            targets = tuple(
                FabricTarget(id=model)
                for model in (
                    "auto",
                    "allam-2-7b",
                    "claude-opus-4-5",
                    "claude-sonnet-4-5",
                    "gemini-3.6-flash",
                    "gemini-3.5-flash",
                    "gpt-oss-120b",
                )
            )
            return fabric, FabricHealth("READY", True, "test"), targets
        return None, FabricHealth("UNAVAILABLE", False, "test"), ()

    monkeypatch.setattr("everstate.council_cli._safe_fabric", fake_safe)
    packet = ContinuationPacket(project_id="proj_remote", state_version=9)

    participants, _, _ = _select_participants(
        packet,
        ("architect", "critic", "verifier"),
        3,
    )

    assert [participant.model for participant in participants] == [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gpt-oss-120b",
    ]
