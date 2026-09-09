from __future__ import annotations

import json

import typer
from typer.testing import CliRunner

from everstate.execution_config import (
    ExecutionSettings,
    config_path,
    load_execution_settings,
    private_file_permissions_enforced,
    save_execution_settings,
)
from everstate.freellmapi_fabric import FreeLLMAPIConfig
from everstate.omniroute_fabric import OmniRouteConfig
from everstate.provider_fabric import FabricHealth
from everstate.setup_wizard_cli import register as register_setup
from everstate.ypipe_fabric import YpipeConfig


def test_saved_endpoints_are_used_by_runtime_configs(monkeypatch, tmp_path):
    monkeypatch.setenv("EVERSTATE_HOME", str(tmp_path))
    settings = ExecutionSettings(
        policy="cloud-preferred",
        ypipe_url="http://127.0.0.1:4100/v1",
        freellmapi_url="http://127.0.0.1:3101/v1",
        freellmapi_api_key="freellmapi-test-token",
        omniroute_url="http://127.0.0.1:21128/v1",
    )
    save_execution_settings(settings)

    assert YpipeConfig.from_env().base_url == settings.ypipe_url
    assert FreeLLMAPIConfig.from_env().base_url == settings.freellmapi_url
    assert FreeLLMAPIConfig.from_env().api_key == settings.freellmapi_api_key
    assert OmniRouteConfig.from_env().base_url == settings.omniroute_url


def test_environment_overrides_persisted_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("EVERSTATE_HOME", str(tmp_path))
    save_execution_settings(
        ExecutionSettings(
            ypipe_url="http://127.0.0.1:4100/v1",
            freellmapi_url="http://127.0.0.1:3101/v1",
            freellmapi_api_key="saved-token",
            omniroute_url="http://127.0.0.1:21128/v1",
        )
    )
    monkeypatch.setenv("EVERSTATE_YPIPE_URL", "http://127.0.0.1:4200/v1")
    monkeypatch.setenv("EVERSTATE_FREELLMAPI_URL", "http://127.0.0.1:3201/v1")
    monkeypatch.setenv("EVERSTATE_FREELLMAPI_API_KEY", "env-token")
    monkeypatch.setenv("EVERSTATE_OMNIROUTE_URL", "http://127.0.0.1:22128/v1")

    assert YpipeConfig.from_env().base_url == "http://127.0.0.1:4200/v1"
    assert FreeLLMAPIConfig.from_env().base_url == "http://127.0.0.1:3201/v1"
    assert FreeLLMAPIConfig.from_env().api_key == "env-token"
    assert OmniRouteConfig.from_env().base_url == "http://127.0.0.1:22128/v1"


def test_malformed_persisted_settings_fail_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("EVERSTATE_HOME", str(tmp_path))
    path = config_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "policy": 17,
                "ypipe_enabled": "yes",
                "ypipe_url": [],
                "freellmapi_enabled": None,
                "freellmapi_url": "   ",
                "freellmapi_api_key": {"secret": True},
                "omniroute_enabled": 1,
                "omniroute_url": False,
            }
        ),
        encoding="utf-8",
    )

    loaded = load_execution_settings()
    defaults = ExecutionSettings()
    assert loaded == defaults


def test_setup_yes_is_idempotent_and_preserves_saved_values(monkeypatch, tmp_path):
    monkeypatch.setenv("EVERSTATE_HOME", str(tmp_path))
    original = ExecutionSettings(
        policy="cloud-preferred",
        ypipe_enabled=True,
        ypipe_url="http://127.0.0.1:4100/v1",
        freellmapi_enabled=True,
        freellmapi_url="http://127.0.0.1:3101/v1",
        freellmapi_api_key="persist-me",
        omniroute_enabled=True,
        omniroute_url="http://127.0.0.1:21128/v1",
    )
    saved_path = save_execution_settings(original)
    assert private_file_permissions_enforced(saved_path) is True

    monkeypatch.setattr(
        "everstate.setup_wizard_cli._probe",
        lambda factory: FabricHealth(status="READY", ready=True, detail="test ready"),
    )

    app = typer.Typer()
    register_setup(app)
    result = CliRunner().invoke(app, ["--yes", "--no-browser"])

    assert result.exit_code == 0, result.output
    assert load_execution_settings() == original
    assert private_file_permissions_enforced(saved_path) is True
