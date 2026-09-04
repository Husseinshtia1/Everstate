from __future__ import annotations

import pytest

from auth import normalize_redirect


def test_preserves_query_string() -> None:
    assert (
        normalize_redirect("https://app.example.com/callback?code=abc&state=xyz")
        == "https://app.example.com/callback?code=abc&state=xyz"
    )


def test_rejects_untrusted_redirect_host() -> None:
    with pytest.raises(ValueError, match="untrusted redirect host"):
        normalize_redirect("https://evil.example/callback?code=abc")
