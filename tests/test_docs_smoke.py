from pathlib import Path


def test_ubuntu_first_run_assets_exist() -> None:
    assert Path("scripts/bootstrap_ubuntu.sh").is_file()
    assert Path("docs/UBUNTU_FIRST_RUN.md").is_file()
