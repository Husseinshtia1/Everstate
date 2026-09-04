from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


def _candidate_executables(executable: str) -> list[Path]:
    candidates: list[Path] = []

    override = os.environ.get(f"EVERSTATE_{executable.upper()}_BIN")
    if override:
        candidates.append(Path(override).expanduser())

    prefix = os.environ.get("NPM_CONFIG_PREFIX")
    if prefix:
        candidates.append(Path(prefix).expanduser() / "bin" / executable)

    home = Path.home()
    candidates.extend(
        [
            home / ".npm-global" / "bin" / executable,
            home / ".local" / "bin" / executable,
        ]
    )
    return candidates


@dataclass(frozen=True)
class ProviderAdapter:
    name: str
    executable: str

    def resolve_executable(self) -> str | None:
        on_path = shutil.which(self.executable)
        if on_path:
            return on_path

        for candidate in _candidate_executables(self.executable):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        return None

    def available(self) -> bool:
        return self.resolve_executable() is not None

    def interactive_command(self, prompt: str) -> list[str]:
        return [self.resolve_executable() or self.executable, prompt]

    def launch(self, root: Path, prompt: str) -> int:
        executable = self.resolve_executable()
        if executable is None:
            raise FileNotFoundError(
                f"{self.executable!r} is not available. Everstate checked PATH and common user install locations. "
                f"Install or configure {self.name}, or set EVERSTATE_{self.executable.upper()}_BIN."
            )
        completed = subprocess.run([executable, prompt], cwd=root.resolve(), check=False)
        return completed.returncode


PROVIDERS: dict[str, ProviderAdapter] = {
    "claude": ProviderAdapter(name="Claude Code", executable="claude"),
    "codex": ProviderAdapter(name="Codex", executable="codex"),
}


def get_provider(name: str) -> ProviderAdapter:
    key = name.strip().lower()
    try:
        return PROVIDERS[key]
    except KeyError as exc:
        supported = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"Unsupported provider {name!r}. Supported providers: {supported}") from exc
