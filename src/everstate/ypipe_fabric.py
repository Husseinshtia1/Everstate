from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse

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
            base_url=os.environ.get("EVERSTATE_YPIPE_URL", cls.base_url),
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
            raise YpipeError(f"Ypipe returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise YpipeError(f"Ypipe request failed: {exc}") from exc
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise YpipeError("Ypipe returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise YpipeError("Ypipe returned a non-object JSON response")
        return decoded

    def health(self) -> FabricHealth:
        try:
            targets = self.discover_targets()
        except YpipeError as exc:
            return FabricHealth(status="UNAVAILABLE", ready=False, detail=str(exc))
        if not targets:
            return FabricHealth(
                status="DEGRADED",
                ready=False,
                detail="Ypipe is reachable but reported no local models.",
            )
        return FabricHealth(
            status="READY",
            ready=True,
            detail=f"Ypipe is reachable with {len(targets)} local model target(s).",
        )

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
            owned_by = row.get("owned_by") if isinstance(row.get("owned_by"), str) else "ypipe-local"
            targets.append(FabricTarget(id=model_id, provider=owned_by, model=model_id))
        return tuple(targets)

    def selected_model(self) -> str | None:
        return self.config.model

    def resolve_model(self) -> str:
        targets = self.discover_targets()
        if self.config.model:
            if self.config.model not in {target.id for target in targets}:
                raise YpipeError(f"Configured Ypipe model {self.config.model!r} is not in the live model catalog")
            return self.config.model
        if not targets:
            raise YpipeError("Ypipe reported no local models")
        return targets[0].id

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
        payload: dict,
        *,
        timeout: float | None = None,
    ) -> dict:
        """Invoke a SmartPipe that Ypipe has explicitly published as a REST endpoint.

        `endpoint` may be a path relative to the Ypipe server origin or an absolute
        URL. Remote absolute URLs remain forbidden unless allow_remote is enabled.
        """
        if not endpoint.strip():
            raise ValueError("SmartPipe endpoint must not be empty")
        if endpoint.startswith(("http://", "https://")):
            target_url = endpoint
        else:
            base = self._base_url
            parsed = urlparse(base)
            origin = f"{parsed.scheme}://{parsed.netloc}/"
            target_url = urljoin(origin, endpoint.lstrip("/"))
        parsed_target = urlparse(target_url)
        if not self.config.allow_remote and not _is_loopback_host(parsed_target.hostname):
            raise ValueError("SmartPipe endpoint must stay local unless remote Ypipe is explicitly allowed")
        return self._request_json("POST", target_url, payload=payload, timeout=timeout)


class YpipeMcpClient:
    """Minimal MCP Streamable HTTP client for Ypipe-managed MCP integrations.

    Supports JSON responses and the common SSE `data:` envelope returned by
    Streamable HTTP servers. It intentionally exposes only initialize, tools/list,
    and tools/call required by Everstate's integration boundary.
    """

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 5.0,
        opener: Callable[..., object] = urllib.request.urlopen,
        allow_remote: bool = False,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("MCP URL must be an absolute http(s) URL")
        if not allow_remote and not _is_loopback_host(parsed.hostname):
            raise ValueError("Ypipe MCP endpoint must be local unless explicitly allowed")
        self.url = url
        self.timeout = timeout
        self._opener = opener
        self._next_id = 1

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        try:
            response = self._opener(request, timeout=self.timeout)
            text = response.read().decode("utf-8")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, UnicodeDecodeError) as exc:
            raise YpipeError(f"Ypipe MCP request failed: {exc}") from exc

        candidates: Iterable[str]
        stripped = text.strip()
        if stripped.startswith("{"):
            candidates = (stripped,)
        else:
            candidates = (
                line[5:].strip()
                for line in stripped.splitlines()
                if line.startswith("data:") and line[5:].strip() and line[5:].strip() != "[DONE]"
            )
        decoded: dict | None = None
        for candidate in candidates:
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("id") == request_id:
                decoded = value
                break
        if decoded is None:
            raise YpipeError("Ypipe MCP returned no matching JSON-RPC response")
        if "error" in decoded:
            raise YpipeError(f"Ypipe MCP error: {decoded['error']}")
        result = decoded.get("result")
        if not isinstance(result, dict):
            raise YpipeError("Ypipe MCP response is missing an object result")
        return result

    def initialize(self) -> dict:
        return self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
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
            raise ValueError("MCP tool name must not be empty")
        return self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
