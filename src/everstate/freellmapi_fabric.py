from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

from .execution_config import configured_value
from .provider_fabric import FabricHealth, FabricResponse, FabricTarget


class FreeLLMAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class FreeLLMAPIConfig:
    base_url: str = "http://127.0.0.1:3001/v1"
    api_key: str | None = field(default=None, repr=False)
    timeout: float = 5.0

    @classmethod
    def from_env(cls) -> "FreeLLMAPIConfig":
        timeout_raw = os.environ.get("EVERSTATE_FREELLMAPI_TIMEOUT", "5.0")
        try:
            timeout = float(timeout_raw)
        except ValueError as exc:
            raise ValueError("EVERSTATE_FREELLMAPI_TIMEOUT must be a number") from exc
        if timeout <= 0:
            raise ValueError("EVERSTATE_FREELLMAPI_TIMEOUT must be > 0")
        return cls(
            base_url=configured_value("EVERSTATE_FREELLMAPI_URL", "freellmapi_url", cls.base_url) or cls.base_url,
            api_key=os.environ.get("EVERSTATE_FREELLMAPI_API_KEY")
            or configured_value("EVERSTATE_FREELLMAPI_API_KEY", "freellmapi_api_key"),
            timeout=timeout,
        )


class FreeLLMAPIFabric:
    """OpenAI-compatible adapter for a locally hosted FreeLLMAPI router.

    FreeLLMAPI may route requests to remote providers. Everstate therefore treats
    this fabric as remote/free capacity and never selects it for local-only work.
    """

    name = "freellmapi"

    def __init__(
        self,
        config: FreeLLMAPIConfig | None = None,
        *,
        opener: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        self.config = config or FreeLLMAPIConfig.from_env()
        self._opener = opener
        parsed = urlparse(self.config.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("FreeLLMAPI base URL must be an absolute http(s) URL")
        self._base_url = self.config.base_url.rstrip("/")

    def _request_json(self, method: str, path: str, *, payload: dict | None = None, timeout: float | None = None) -> dict:
        headers = {"Accept": "application/json"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = urllib.request.Request(
            f"{self._base_url}/{path.lstrip('/')}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            response = self._opener(request, timeout=timeout or self.config.timeout)
            raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise FreeLLMAPIError(f"FreeLLMAPI HTTP {exc.code}: {detail or exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FreeLLMAPIError(f"FreeLLMAPI request failed: {exc}") from exc
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FreeLLMAPIError("FreeLLMAPI returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise FreeLLMAPIError("FreeLLMAPI returned a non-object JSON response")
        return decoded

    def discover_targets(self) -> tuple[FabricTarget, ...]:
        payload = self._request_json("GET", "models")
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise FreeLLMAPIError("FreeLLMAPI /models response is missing a data list")
        targets: list[FabricTarget] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = row.get("id")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            provider = row.get("owned_by") if isinstance(row.get("owned_by"), str) else None
            targets.append(FabricTarget(id=model_id, provider=provider, model=model_id))
        return tuple(targets)

    def health(self) -> FabricHealth:
        try:
            targets = self.discover_targets()
        except FreeLLMAPIError as exc:
            return FabricHealth(status="UNAVAILABLE", ready=False, detail=str(exc))
        if not targets:
            return FabricHealth(status="DEGRADED", ready=False, detail="FreeLLMAPI is reachable but reported no models.")
        return FabricHealth(status="READY", ready=True, detail=f"FreeLLMAPI is reachable with {len(targets)} model target(s).")

    def execute(self, *, model: str, messages: list[dict], timeout: float | None = None) -> FabricResponse:
        if not model.strip():
            raise ValueError("model must not be empty")
        if not messages:
            raise ValueError("messages must not be empty")
        payload = self._request_json(
            "POST",
            "chat/completions",
            payload={"model": model, "messages": messages, "stream": False},
            timeout=timeout,
        )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise FreeLLMAPIError("FreeLLMAPI chat response is missing choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise FreeLLMAPIError("FreeLLMAPI chat response has an invalid first choice")
        message = first.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise FreeLLMAPIError("FreeLLMAPI chat response is missing message content")
        return FabricResponse(target=model, content=message["content"], raw=payload)
