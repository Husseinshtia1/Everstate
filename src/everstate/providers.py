from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProviderAdapter:
    name: str
    executable: str

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def interactive_command(self, prompt: str) -> list[str]:
        return [self.executable, prompt]

    def launch(self, root: Path, prompt: str) -> int:
        if not self.available():
            raise FileNotFoundError(
                f"{self.executable!r} is not available on PATH. Install or configure {self.name} first."
            )
        completed = subprocess.run(self.interactive_command(prompt), cwd=root.resolve(), check=False)
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
