from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse

from .execution_config import configured_value
from .provider_fabric import FabricHealth, FabricResponse, FabricTarget


class YpipeError(RuntimeError):
    """Raised when the Ypipe public integration surface cannot be used safely."""


@dataclass(frozen=True)
class YpipeConfig:
    # Ypipe documents OpenAI compatibility but not a stable port in the public README.
    # 4000 is the historical local default; operators can/should override explicitly.
    base_url: str = "http://127.0.0.1:4000/v1"
    api_key: str | None = field(default=None, repr=False)
    timeout: float = 5.0
    allow_remote: bool = False
    mcp_url: str | None = None
    model: str | None = None
    smartpipe_endpoint: str | None = None

    @classmethod
    def from_env(cls) -> "YpipeConfig":
        timeout_raw = os.environ.get("EVERSTATE_YPIPE_TIMEOUT", "5.0")
        try:
            timeout = float(timeout_raw)
        except ValueError as exc:
            raise ValueError("EVERSTATE_YPIPE_TIMEOUT must be a number") from exc
        if timeout <= 0:
            raise ValueError("EVERSTATE_YPIPE_TIMEOUT must be > 0")
        allow_remote = os.environ.get("EVERSTATE_YPIPE_ALLOW_REMOTE", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return cls(
            base_url=configured_value("EVERSTATE_YPIPE_URL", "ypipe_url", cls.base_url) or cls.base_url,
            api_key=os.environ.get("EVERSTATE_YPIPE_API_KEY"),
            timeout=timeout,
            allow_remote=allow_remote,
            mcp_url=os.environ.get("EVERSTATE_YPIPE_MCP_URL") or None,
            model=os.environ.get("EVERSTATE_YPIPE_MODEL") or None,
            smartpipe_endpoint=os.environ.get("EVERSTATE_YPIPE_SMARTPIPE_ENDPOINT") or None,
        )


def _is_loopback_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    return hostname.lower() in {"127.0.0.1", "localhost", "::1"}


class YpipeFabric:
    """Public-contract integration for Ypipe local inference and SmartPipe REST endpoints.

    Everstate remains authoritative for canonical project state. Ypipe is treated only
    as a sovereign execution fabric. No Ypipe source code or proprietary internals are
    embedded or depended upon here.
    """

    name = "ypipe"

    def __init__(
        self,
        config: YpipeConfig | None = None,
        *,
        opener: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        self.config = config or YpipeConfig.from_env()
        self._opener = opener
        parsed = urlparse(self.config.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Ypipe base URL must be an absolute http(s) URL")
        if not self.config.allow_remote and not _is_loopback_host(parsed.hostname):
            raise ValueError(
                "Ypipe is local-only by default. Set EVERSTATE_YPIPE_ALLOW_REMOTE=true "
                "only when the operator explicitly accepts a non-loopback Ypipe endpoint."
            )
        self._base_url = self.config.base_url.rstrip("/")

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        payload: dict | None = None,
        timeout: float | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        headers = {"Accept": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            response = self._opener(request, timeout=timeout or self.config.timeout)
            raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise YpipeError(f"Ypipe HTTP {exc.code}: {detail or exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise YpipeError(f"Ypipe request failed: {exc}") from exc

        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise YpipeError("Ypipe returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise YpipeError("Ypipe returned a non-object JSON response")
        return decoded

    def discover_targets(self) -> tuple[FabricTarget, ...]:
        payload = self._request_json("GET", f"{self._base_url}/models")
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise YpipeError("Ypipe /models response is missing a data list")
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
        except YpipeError as exc:
            return FabricHealth(status="UNAVAILABLE", ready=False, detail=str(exc))
        if not targets:
            return FabricHealth(status="DEGRADED", ready=False, detail="Ypipe is reachable but reported no local models.")
        return FabricHealth(status="READY", ready=True, detail=f"Ypipe is reachable with {len(targets)} local model target(s).")

    def execute(
        self,
        *,
        model: str,
        messages: list[dict],
        timeout: float | None = None,
    ) -> FabricResponse:
        if not model.strip():
            raise ValueError("model must not be empty")
        if not messages:
            raise ValueError("messages must not be empty")
        payload = self._request_json(
            "POST",
            f"{self._base_url}/chat/completions",
            payload={"model": model, "messages": messages, "stream": False},
            timeout=timeout,
        )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise YpipeError("Ypipe chat response is missing choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise YpipeError("Ypipe chat response has an invalid first choice")
        message = first.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise YpipeError("Ypipe chat response is missing message content")
        return FabricResponse(target=model, content=message["content"], raw=payload)

    def run_smartpipe(
        self,
        endpoint: str,
        *,
        payload: dict,
        timeout: float | None = None,
    ) -> dict:
        if not endpoint.strip():
            raise ValueError("SmartPipe endpoint must not be empty")
        url = urljoin(f"{self._base_url}/", endpoint.lstrip("/"))
        return self._request_json("POST", url, payload=payload, timeout=timeout)

    def resolve_model(self, requested: str | None = None) -> str:
        configured = requested or self.config.model
        targets = self.discover_targets()
        if configured:
            if configured not in {target.id for target in targets}:
                raise YpipeError(f"Configured Ypipe model {configured!r} is not in the live model catalog")
            return configured
        if not targets:
            raise YpipeError("Ypipe reported no local models")
        return targets[0].id


class YpipeMcpClient:
    """Minimal MCP-over-HTTP client for Ypipe public MCP surfaces."""

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 5.0,
        allow_remote: bool = False,
        opener: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Ypipe MCP URL must be an absolute http(s) URL")
        if not allow_remote and not _is_loopback_host(parsed.hostname):
            raise ValueError("Ypipe MCP is local-only unless remote access is explicitly enabled")
        self.url = url
        self.timeout = timeout
        self._opener = opener
        self._request_id = 0
        self._session_id: str | None = None

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._request_id += 1
        request_id = self._request_id
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            response = self._opener(request, timeout=self.timeout)
            session_id = response.headers.get("Mcp-Session-Id") if hasattr(response, "headers") else None
            if session_id:
                self._session_id = session_id
            raw = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "") if hasattr(response, "headers") else ""
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise YpipeError(f"Ypipe MCP request failed: {exc}") from exc

        envelope = self._decode_mcp_envelope(raw, content_type)
        if envelope.get("id") != request_id:
            raise YpipeError("Ypipe MCP response id does not match request id")
        if envelope.get("error"):
            raise YpipeError(f"Ypipe MCP error: {envelope['error']}")
        result = envelope.get("result")
        if not isinstance(result, dict):
            raise YpipeError("Ypipe MCP response is missing a result object")
        return result

    @staticmethod
    def _decode_mcp_envelope(raw: str, content_type: str) -> dict:
        if "text/event-stream" in content_type:
            data_lines = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
            if not data_lines:
                raise YpipeError("Ypipe MCP SSE response contains no data event")
            raw = data_lines[-1]
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise YpipeError("Ypipe MCP returned invalid JSON") from exc
        if not isinstance(envelope, dict):
            raise YpipeError("Ypipe MCP returned a non-object response")
        return envelope

    def initialize(self) -> dict:
        return self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "everstate", "version": "0.1"},
            },
        )

    def list_tools(self) -> tuple[dict, ...]:
        result = self._rpc("tools/list", {})
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise YpipeError("Ypipe MCP tools/list response is missing tools")
        return tuple(tool for tool in tools if isinstance(tool, dict))

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        if not name.strip():
            raise ValueError("tool name must not be empty")
        return self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
