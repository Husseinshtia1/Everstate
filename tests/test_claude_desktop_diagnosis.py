from pathlib import Path

from everstate.claude_desktop import diagnose_claude_desktop_profiles


def test_diagnosis_detects_cloud_renderer_profile_without_reading_contents(tmp_path: Path) -> None:
    root = tmp_path / ".config" / "Claude"
    (root / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb").mkdir(parents=True)
    (root / "Local Storage" / "leveldb").mkdir(parents=True)
    (root / "Cookies").write_text("secret-cookie-bytes-must-not-be-read", encoding="utf-8")

    items = diagnose_claude_desktop_profiles(tmp_path)
    linux = next(item for item in items if item.profile_root == root)

    assert linux.exists is True
    assert linux.claude_ai_indexeddb_exists is True
    assert linux.claude_ai_local_storage_exists is True
    assert linux.cookies_store_exists is True
    assert linux.spaces_file_count == 0
    assert linux.has_cloud_renderer_profile is True
    assert linux.has_local_cowork_inventory is False


def test_diagnosis_counts_spaces_files_structurally(tmp_path: Path) -> None:
    root = tmp_path / ".config" / "Claude"
    store = root / "local-agent-mode-sessions" / "acct" / "org"
    store.mkdir(parents=True)
    (store / "spaces.json").write_text("{not parsed by diagnosis}", encoding="utf-8")

    items = diagnose_claude_desktop_profiles(tmp_path)
    linux = next(item for item in items if item.profile_root == root)

    assert linux.local_agent_root_exists is True
    assert linux.spaces_file_count == 1
    assert linux.has_local_cowork_inventory is True
