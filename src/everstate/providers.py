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
    prompt_args: tuple[str, ...] = ()
    model_env: str | None = None
    default_model: str | None = None

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

    def selected_model(self) -> str | None:
        if self.model_env:
            configured = os.environ.get(self.model_env)
            if configured:
                return configured.strip()
        return self.default_model

    def effective_prompt_args(self) -> list[str]:
        args = list(self.prompt_args)
        model = self.selected_model()
        if model is not None:
            args.extend(["-m", model])
        return args

    def interactive_command(self, prompt: str) -> list[str]:
        return [self.resolve_executable() or self.executable, *self.effective_prompt_args(), prompt]

    def launch(self, root: Path, prompt: str) -> int:
        executable = self.resolve_executable()
        if executable is None:
            raise FileNotFoundError(
                f"{self.executable!r} is not available. Everstate checked PATH and common user install locations. "
                f"Install or configure {self.name}, or set EVERSTATE_{self.executable.upper()}_BIN."
            )
        completed = subprocess.run(
            [executable, *self.effective_prompt_args(), prompt],
            cwd=root.resolve(),
            check=False,
        )
        return completed.returncode


PROVIDERS: dict[str, ProviderAdapter] = {
    "claude": ProviderAdapter(name="Claude Code", executable="claude"),
    "codex": ProviderAdapter(name="Codex", executable="codex"),
    "gemini": ProviderAdapter(name="Gemini CLI", executable="gemini", prompt_args=("-i",)),
    "codex-ollama": ProviderAdapter(
        name="Codex + Ollama (local)",
        executable="codex",
        prompt_args=("--oss", "--local-provider", "ollama"),
        model_env="EVERSTATE_OLLAMA_MODEL",
        default_model="gpt-oss:20b",
    ),
}


def get_provider(name: str) -> ProviderAdapter:
    key = name.strip().lower()
    try:
        return PROVIDERS[key]
    except KeyError as exc:
        supported = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"Unsupported provider {name!r}. Supported providers: {supported}") from exc
