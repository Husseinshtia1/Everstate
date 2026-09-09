from __future__ import annotations

from everstate.continuity import ContinuationPacket
from everstate.council_cli import _select_participants
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
