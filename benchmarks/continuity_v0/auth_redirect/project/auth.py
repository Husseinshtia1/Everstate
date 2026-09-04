from __future__ import annotations

from urllib.parse import urlparse


ALLOWED_HOST = "app.example.com"


def normalize_redirect(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.netloc != ALLOWED_HOST:
        raise ValueError("untrusted redirect host")

    path = parsed.path or "/"
    # BUG: query parameters are currently lost here.
    return f"https://{ALLOWED_HOST}{path}"
