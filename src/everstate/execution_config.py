from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


_VALID_POLICIES = {"auto", "local-only", "cloud-allowed", "cloud-preferred"}


@dataclass(frozen=True)
class ExecutionSettings:
    policy: str = "auto"
    ypipe_enabled: bool = True
    ypipe_url: str = "http://127.0.0.1:4000/v1"
    freellmapi_enabled: bool = True
    freellmapi_url: str = "http://127.0.0.1:3001/v1"
    freellmapi_api_key: str | None = None
    omniroute_enabled: bool = True
    omniroute_url: str = "http://127.0.0.1:20128/v1"


def config_path() -> Path:
    root = Path(os.environ.get("EVERSTATE_HOME", str(Path.home()))).expanduser().resolve()
    return root / ".everstate" / "execution.json"


def _string(raw: object, default: str) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return default


def _optional_string(raw: object, default: str | None) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        value = raw.strip()
        return value or None
    return default


def _bool(raw: object, default: bool) -> bool:
    return raw if isinstance(raw, bool) else default


def _settings_from_mapping(raw: dict) -> ExecutionSettings:
    defaults = ExecutionSettings()
    policy = _string(raw.get("policy"), defaults.policy).lower()
    if policy not in _VALID_POLICIES:
        policy = defaults.policy
    return ExecutionSettings(
        policy=policy,
        ypipe_enabled=_bool(raw.get("ypipe_enabled"), defaults.ypipe_enabled),
        ypipe_url=_string(raw.get("ypipe_url"), defaults.ypipe_url),
        freellmapi_enabled=_bool(raw.get("freellmapi_enabled"), defaults.freellmapi_enabled),
        freellmapi_url=_string(raw.get("freellmapi_url"), defaults.freellmapi_url),
        freellmapi_api_key=_optional_string(raw.get("freellmapi_api_key"), defaults.freellmapi_api_key),
        omniroute_enabled=_bool(raw.get("omniroute_enabled"), defaults.omniroute_enabled),
        omniroute_url=_string(raw.get("omniroute_url"), defaults.omniroute_url),
    )


def load_execution_settings() -> ExecutionSettings:
    path = config_path()
    if not path.exists():
        return ExecutionSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ExecutionSettings()
    if not isinstance(raw, dict):
        return ExecutionSettings()
    return _settings_from_mapping(raw)


def save_execution_settings(settings: ExecutionSettings) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path


def configured_value(env_name: str, setting_name: str, default: str | None = None) -> str | None:
    value = os.environ.get(env_name)
    if value is not None:
        return value
    settings = load_execution_settings()
    configured = getattr(settings, setting_name, default)
    return configured if isinstance(configured, str) or configured is None else default


def fabric_enabled(name: str) -> bool:
    settings = load_execution_settings()
    mapping = {
        "ypipe": settings.ypipe_enabled,
        "freellmapi": settings.freellmapi_enabled,
        "omniroute": settings.omniroute_enabled,
    }
    if name not in mapping:
        raise KeyError(name)
    return bool(mapping[name])


def configured_policy() -> str:
    return load_execution_settings().policy
