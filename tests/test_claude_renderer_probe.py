from pathlib import Path

from everstate.claude_renderer_probe import probe_claude_renderer


def _proc(root: Path, pid: str, cmdline: str) -> None:
    path = root / pid
    path.mkdir(parents=True)
    (path / "cmdline").write_bytes(cmdline.replace(" ", "\0").encode())


def test_probe_detects_loopback_debugging_flags(tmp_path: Path) -> None:
    _proc(
        tmp_path,
        "123",
        "/opt/Claude/claude --remote-debugging-address=127.0.0.1 --remote-debugging-port=9223",
    )
    result = probe_claude_renderer(tmp_path)
    assert result.claude_processes == 1
    assert result.remote_debugging_enabled is True
    assert result.port == 9223
    assert result.address == "127.0.0.1"
    assert result.loopback_only is True


def test_probe_rejects_non_loopback_channel(tmp_path: Path) -> None:
    _proc(tmp_path, "123", "/opt/Claude/claude --remote-debugging-address=0.0.0.0 --remote-debugging-port=9223")
    result = probe_claude_renderer(tmp_path)
    assert result.remote_debugging_enabled is True
    assert result.loopback_only is False
    assert result.safe_for_readonly_probe is False


def test_probe_without_debugging_does_not_infer_readiness(tmp_path: Path) -> None:
    _proc(tmp_path, "123", "/opt/Claude/claude")
    result = probe_claude_renderer(tmp_path)
    assert result.claude_processes == 1
    assert result.remote_debugging_enabled is False
    assert result.port is None
    assert result.safe_for_readonly_probe is False
