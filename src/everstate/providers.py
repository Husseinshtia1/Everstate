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
    handoff_slug: str | None = None
    model_flag: str = "-m"
    prompt_separator: tuple[str, ...] = ()
    automation_args: tuple[str, ...] | None = None
    automation_probe_args: tuple[str, ...] | None = None

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

    @property
    def automation_supported(self) -> bool:
        return self.automation_args is not None

    def automation_preflight(self, timeout: float = 10.0) -> tuple[bool, str]:
        """Validate a headless provider without sending an inference request."""
        if not self.automation_supported:
            return False, f"{self.name} has no verified non-interactive automation contract."
        executable = self.resolve_executable()
        if executable is None:
            return False, f"{self.executable!r} is not installed or not executable."
        if self.automation_probe_args is None:
            return True, f"{self.name} executable is available."
        try:
            completed = subprocess.run(
                [executable, *self.automation_probe_args],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"{self.name} readiness probe failed: {exc}"
        detail = (completed.stdout or completed.stderr).strip()
        if completed.returncode != 0:
            return False, detail or f"{self.name} readiness probe exited {completed.returncode}."
        return True, detail or f"{self.name} headless automation is ready."

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
            args.extend([self.model_flag, model])
        args.extend(self.prompt_separator)
        return args

    def interactive_command(self, prompt: str) -> list[str]:
        return [self.resolve_executable() or self.executable, *self.effective_prompt_args(), prompt]

    def automation_command(self, prompt: str) -> list[str]:
        if self.automation_args is None:
            raise RuntimeError(
                f"{self.name} does not yet have a verified non-interactive automation contract in Everstate."
            )
        return [self.resolve_executable() or self.executable, *self.automation_args, prompt]

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

    def launch_automated(self, root: Path, prompt: str) -> int:
        executable = self.resolve_executable()
        if executable is None:
            raise FileNotFoundError(
                f"{self.executable!r} is not available. Everstate checked PATH and common user install locations. "
                f"Install or configure {self.name}, or set EVERSTATE_{self.executable.upper()}_BIN."
            )
        command = self.automation_command(prompt)
        command[0] = executable
        completed = subprocess.run(command, cwd=root.resolve(), check=False)
        return completed.returncode

    @property
    def handoff_name(self) -> str:
        return self.handoff_slug or self.executable


PROVIDERS: dict[str, ProviderAdapter] = {
    "claude": ProviderAdapter(name="Claude Code", executable="claude"),
    "codex": ProviderAdapter(
        name="Codex",
        executable="codex",
        # Current Codex exposes non-interactive execution through `codex exec`.
        # Keep the benchmark sandboxed and remove approval prompts explicitly
        # through config overrides instead of relying on legacy convenience flags.
        automation_args=(
            "-c",
            'approval_policy="never"',
            "-c",
            "sandbox_workspace_write.network_access=false",
            "exec",
            "--sandbox",
            "workspace-write",
            "--ephemeral",
        ),
        automation_probe_args=("login", "status"),
    ),
    "gemini": ProviderAdapter(name="Gemini CLI", executable="gemini", prompt_args=("-i",)),
    "codex-ollama": ProviderAdapter(
        name="Codex + Ollama (local)",
        executable="codex",
        prompt_args=("--oss", "--local-provider", "ollama"),
        model_env="EVERSTATE_OLLAMA_MODEL",
        default_model="gpt-oss:20b",
        handoff_slug="codex-ollama",
    ),
    "codex-omniroute": ProviderAdapter(
        name="Codex via OmniRoute",
        executable="omniroute",
        prompt_args=("run", "codex"),
        model_env="EVERSTATE_OMNIROUTE_MODEL",
        model_flag="--model",
        prompt_separator=("--",),
        handoff_slug="codex-omniroute",
    ),
}


def get_provider(name: str) -> ProviderAdapter:
    key = name.strip().lower()
    try:
        return PROVIDERS[key]
    except KeyError as exc:
        supported = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"Unsupported provider {name!r}. Supported providers: {supported}") from exc
