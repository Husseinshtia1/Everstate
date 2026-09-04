from __future__ import annotations

from auth import normalize_redirect


assert (
    normalize_redirect("https://app.example.com/callback?code=abc&state=xyz")
    == "https://app.example.com/callback?code=abc&state=xyz"
)

try:
    normalize_redirect("https://evil.example/callback?code=abc")
except ValueError as exc:
    assert "untrusted redirect host" in str(exc)
else:
    raise AssertionError("untrusted redirect host must be rejected")

print("continuity scenario verification passed")
