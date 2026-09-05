from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_OLLAMA_API = "http://127.0.0.1:11434"


@dataclass(frozen=True)
class OllamaRuntimeStatus:
    reachable: bool
    models: tuple[str, ...]
    detail: str
    base_url: str


def ollama_base_url() -> str:
    configured = os.environ.get("OLLAMA_HOST", "").strip()
    if not configured:
        return DEFAULT_OLLAMA_API
    if "://" not in configured:
        configured = f"http://{configured}"
    return configured.rstrip("/")


def _is_local_host(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def probe_ollama_runtime(*, timeout: float = 2.0) -> OllamaRuntimeStatus:
    base_url = ollama_base_url()
    if not _is_local_host(base_url):
        return OllamaRuntimeStatus(
            reachable=False,
            models=(),
            detail="OLLAMA_HOST points to a non-local host; Everstate local fallback only probes localhost by default.",
            base_url=base_url,
        )

    request = Request(f"{base_url}/api/tags", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return OllamaRuntimeStatus(
            reachable=False,
            models=(),
            detail=f"Ollama local API is not reachable at {base_url}: {exc}",
            base_url=base_url,
        )

    names: list[str] = []
    for model in payload.get("models", []):
        if not isinstance(model, dict):
            continue
        name = model.get("name") or model.get("model")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())

    return OllamaRuntimeStatus(
        reachable=True,
        models=tuple(sorted(set(names))),
        detail=f"Ollama local API reachable with {len(set(names))} installed model(s).",
        base_url=base_url,
    )


def model_is_installed(selected_model: str, installed_models: tuple[str, ...]) -> bool:
    selected = selected_model.strip()
    if selected in installed_models:
        return True
    # Ollama commonly displays an explicit :latest tag when users configure the bare model name.
    if ":" not in selected and f"{selected}:latest" in installed_models:
        return True
    return False
