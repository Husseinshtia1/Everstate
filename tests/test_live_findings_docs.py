from pathlib import Path


def test_live_ubuntu_findings_doc_exists() -> None:
    assert Path("docs/LIVE_UBUNTU_FINDINGS.md").exists()
