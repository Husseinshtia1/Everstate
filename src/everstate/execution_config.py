from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path


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
    defaults = asdict(ExecutionSettings())
    values = {key: raw.get(key, default) for key, default in defaults.items()}
    return ExecutionSettings(**values)


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
