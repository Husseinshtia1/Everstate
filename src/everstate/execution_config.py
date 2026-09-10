from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


_VALID_POLICIES = {"auto", "local-only", "cloud-allowed", "cloud-preferred"}


def normalize_bearer_token(value: str | None) -> str | None:
    """Normalize and validate an HTTP Bearer token before persistence/use.

    urllib/http.client encodes HTTP header values as latin-1. Provider tokens are
    expected to be printable ASCII without whitespace. Reject placeholders,
    pasted prose, and invisible/non-ASCII characters with an actionable error
    instead of surfacing a low-level codec exception during a health probe.
    """
    if value is None:
        return None
    token = value.strip()
    if not token:
        return None
    if any(char.isspace() for char in token):
        raise ValueError("FreeLLMAPI unified API key must not contain whitespace")
    try:
        token.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(
            "FreeLLMAPI unified API key must contain ASCII characters only; "
            "copy the actual Unified API key from the FreeLLMAPI Keys page, not placeholder text"
        ) from exc
    if any(ord(char) < 0x21 or ord(char) > 0x7E for char in token):
        raise ValueError("FreeLLMAPI unified API key contains invalid control characters")
    return token


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
    persisted_token = _optional_string(raw.get("freellmapi_api_key"), defaults.freellmapi_api_key)
    try:
        persisted_token = normalize_bearer_token(persisted_token)
    except ValueError:
        # Legacy/bad values must never make HTTP header construction crash.
        # Treat them as absent so setup can request a corrected token.
        persisted_token = None
    return ExecutionSettings(
        policy=policy,
        ypipe_enabled=_bool(raw.get("ypipe_enabled"), defaults.ypipe_enabled),
        ypipe_url=_string(raw.get("ypipe_url"), defaults.ypipe_url),
        freellmapi_enabled=_bool(raw.get("freellmapi_enabled"), defaults.freellmapi_enabled),
        freellmapi_url=_string(raw.get("freellmapi_url"), defaults.freellmapi_url),
        freellmapi_api_key=persisted_token,
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


def _restrict_private_file(path: Path) -> None:
    """Restrict a settings file to the current user on POSIX and Windows.

    POSIX mode bits do not represent NTFS ACLs. On Windows use icacls to
    remove inherited ACL entries and grant the current user full control.
    Failing to secure a file that may contain provider credentials is fatal.
    """
    if os.name != "nt":
        os.chmod(path, 0o600)
        return

    identity = os.environ.get("USERNAME", "").strip()
    if not identity:
        try:
            identity = subprocess.run(
                ["whoami"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise OSError("Unable to determine Windows user for private Everstate settings ACL") from exc
    if not identity:
        raise OSError("Unable to determine Windows user for private Everstate settings ACL")

    try:
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{identity}:(F)"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise OSError("Unable to restrict Everstate settings file to the current Windows user") from exc


def private_file_permissions_enforced(path: Path) -> bool:
    """Return whether Everstate's platform-appropriate private-file rule holds."""
    if os.name != "nt":
        return (path.stat().st_mode & 0o777) == 0o600

    try:
        completed = subprocess.run(
            ["icacls", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    acl = completed.stdout.lower()
    forbidden = ("everyone:", "builtin\\users:", "authenticated users:")
    return not any(entry in acl for entry in forbidden)


def save_execution_settings(settings: ExecutionSettings) -> Path:
    normalized_token = normalize_bearer_token(settings.freellmapi_api_key)
    settings = ExecutionSettings(
        policy=settings.policy,
        ypipe_enabled=settings.ypipe_enabled,
        ypipe_url=settings.ypipe_url,
        freellmapi_enabled=settings.freellmapi_enabled,
        freellmapi_url=settings.freellmapi_url,
        freellmapi_api_key=normalized_token,
        omniroute_enabled=settings.omniroute_enabled,
        omniroute_url=settings.omniroute_url,
    )
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _restrict_private_file(tmp)
    tmp.replace(path)
    # Some filesystems can change security metadata on replacement. Re-apply the
    # final-path policy so secrets are never left with best-effort permissions.
    _restrict_private_file(path)
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
