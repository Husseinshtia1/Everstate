from __future__ import annotations

import json

import pytest

from everstate.execution_config import (
    ExecutionSettings,
    load_execution_settings,
    normalize_bearer_token,
    save_execution_settings,
)


def test_normalize_bearer_token_accepts_realistic_ascii_token() -> None:
    token = "freellmapi-abc123_DEF-456"
    assert normalize_bearer_token(token) == token


def test_normalize_bearer_token_rejects_non_ascii_placeholder() -> None:
    with pytest.raises(ValueError, match="ASCII characters only"):
        normalize_bearer_token("ضع_هنا_UNIFIED_API_KEY")


def test_save_execution_settings_rejects_invalid_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EVERSTATE_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="ASCII characters only"):
        save_execution_settings(ExecutionSettings(freellmapi_api_key="مفتاح"))


def test_legacy_invalid_token_is_treated_as_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EVERSTATE_HOME", str(tmp_path))
    path = tmp_path / ".everstate" / "execution.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"policy": "auto", "freellmapi_api_key": "ضع_هنا_UNIFIED_API_KEY"}),
        encoding="utf-8",
    )
    loaded = load_execution_settings()
    assert loaded.freellmapi_api_key is None
