from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .execution_config import ExecutionSettings, load_execution_settings, save_execution_settings
from .freellmapi_fabric import FreeLLMAPIConfig, FreeLLMAPIFabric
from .omniroute_fabric import OmniRouteConfig, OmniRouteFabric
from .provider_fabric import FabricHealth
from .ruflo_orchestrator import RufloOrchestrator
from .ypipe_fabric import YpipeConfig, YpipeFabric

console = Console()


def _probe(factory) -> FabricHealth:
    try:
        return factory().health()
    except (ValueError, OSError, RuntimeError) as exc:
        return FabricHealth(status="UNAVAILABLE", ready=False, detail=str(exc))


def _install_freellmapi() -> tuple[bool, str]:
    if shutil.which("docker") is None:
        return False, "Docker is required by the official FreeLLMAPI one-line installer."
    command = "curl -fsSL https://freellmapi.co/install.sh | bash"
    completed = subprocess.run(["bash", "-lc", command], check=False)
    if completed.returncode != 0:
        return False, f"FreeLLMAPI installer exited with code {completed.returncode}."
    return True, "FreeLLMAPI installer completed."


def _install_ruflo() -> tuple[bool, str]:
    if shutil.which("npm") is None:
        return False, "Ruflo requires Node.js 20+ with npm; npm was not found on PATH."
    completed = subprocess.run(
        ["npm", "install", "-g", "claude-flow@^3"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        suffix = f" Last output: {detail[-1]}" if detail else ""
        return False, f"Ruflo/claude-flow installer exited with code {completed.returncode}.{suffix}"
    return True, "Ruflo/claude-flow v3 installer completed."


def _policy_prompt(default: str = "auto") -> str:
    console.print("\n[bold]Execution policy[/bold]")
    console.print("  [cyan]1[/cyan] Automatic (recommended): local → free remote → cloud")
    console.print("  [cyan]2[/cyan] Local only: never send project state to remote providers")
    console.print("  [cyan]3[/cyan] Cloud preferred: OmniRoute → FreeLLMAPI → local")
    choice = typer.prompt("Choose", default={"auto": "1", "local-only": "2", "cloud-preferred": "3"}.get(default, "1"))
    return {"1": "auto", "2": "local-only", "3": "cloud-preferred"}.get(choice.strip(), default)


def _effective_value(env_name: str, saved: str) -> str:
    value = os.environ.get(env_name)
    return value.strip() if isinstance(value, str) and value.strip() else saved


def _free_needs_credentials(health: FabricHealth) -> bool:
    detail = health.detail.lower()
    return "http 401" in detail or "unauthorized" in detail or "bearer" in detail


def register(app: typer.Typer) -> None:
    @app.command("setup")
    def setup(
        yes: bool = typer.Option(False, "--yes", "-y", help="Accept recommended choices without interactive prompts."),
        install_missing: bool = typer.Option(False, "--install-missing", help="Install supported missing local services such as FreeLLMAPI and Ruflo."),
        freellmapi_token: str | None = typer.Option(None, "--freellmapi-token", help="Unified FreeLLMAPI token; stored in the 0600 Everstate execution config."),
        no_browser: bool = typer.Option(False, "--no-browser", help="Do not open the FreeLLMAPI dashboard when a token/provider setup is needed."),
    ) -> None:
        """Discover, configure, and validate Everstate execution fabrics and orchestration."""
        console.print(Panel.fit("Automatic execution discovery and configuration", title="Everstate Setup"))

        current = load_execution_settings()
        ypipe_url = _effective_value("EVERSTATE_YPIPE_URL", current.ypipe_url)
        free_url = _effective_value("EVERSTATE_FREELLMAPI_URL", current.freellmapi_url)
        omni_url = _effective_value("EVERSTATE_OMNIROUTE_URL", current.omniroute_url)
        effective_free_token = (
            freellmapi_token
            or os.environ.get("EVERSTATE_FREELLMAPI_API_KEY")
            or current.freellmapi_api_key
        )

        ypipe_health = _probe(lambda: YpipeFabric(YpipeConfig(base_url=ypipe_url)))
        free_health = _probe(lambda: FreeLLMAPIFabric(FreeLLMAPIConfig(base_url=free_url, api_key=effective_free_token)))
        omni_health = _probe(lambda: OmniRouteFabric(OmniRouteConfig(base_url=omni_url)))
        ruflo_health = RufloOrchestrator().health()

        table = Table(title="Detected execution and orchestration services")
        table.add_column("Service")
        table.add_column("Role")
        table.add_column("State")
        table.add_column("Ready")
        table.add_column("Endpoint / Version")
        table.add_row("Ypipe", "LOCAL_SOVEREIGN", ypipe_health.status, str(ypipe_health.ready), ypipe_url)
        table.add_row("FreeLLMAPI", "FREE_REMOTE", free_health.status, str(free_health.ready), free_url)
        table.add_row("OmniRoute", "REMOTE_MULTI_PROVIDER", omni_health.status, str(omni_health.ready), omni_url)
        table.add_row(
            "Ruflo",
            "AGENT_ORCHESTRATION",
            "READY" if ruflo_health.ready else "UNAVAILABLE",
            str(ruflo_health.ready),
            ruflo_health.version or "claude-flow v3 required",
        )
        console.print(table)

        if not free_health.ready:
            should_install = install_missing or (not yes and typer.confirm("FreeLLMAPI is not ready. Install/configure it automatically?", default=True))
            if should_install and not _free_needs_credentials(free_health):
                installed, detail = _install_freellmapi()
                console.print(f"[{'green' if installed else 'yellow'}]{detail}[/]")
                if installed:
                    free_health = _probe(
                        lambda: FreeLLMAPIFabric(FreeLLMAPIConfig(base_url=free_url, api_key=effective_free_token))
                    )

        if not ruflo_health.ready and install_missing:
            installed, detail = _install_ruflo()
            console.print(f"[{'green' if installed else 'yellow'}]{detail}[/]")
            if installed:
                ruflo_health = RufloOrchestrator().health()

        if not free_health.ready and _free_needs_credentials(free_health):
            if effective_free_token is None and not yes:
                if not no_browser:
                    webbrowser.open("http://127.0.0.1:3001")
                console.print(
                    "FreeLLMAPI is running but requires its unified token. "
                    "Add provider keys in the local dashboard, then copy the unified token."
                )
                effective_free_token = typer.prompt("FreeLLMAPI unified token", hide_input=True).strip() or None
                free_health = _probe(
                    lambda: FreeLLMAPIFabric(FreeLLMAPIConfig(base_url=free_url, api_key=effective_free_token))
                )
            elif effective_free_token is None:
                console.print(
                    "[yellow]FreeLLMAPI ACTION_REQUIRED: the router is running, but /v1 requires a unified API key. "
                    "Open http://127.0.0.1:3001, add at least one provider key on Keys, copy the unified API key, "
                    "then rerun `everstate setup --freellmapi-token <TOKEN> --yes --no-browser`.[/yellow]"
                )

        policy = current.policy if yes else _policy_prompt(current.policy)
        enable_ypipe = current.ypipe_enabled if yes else typer.confirm("Enable Ypipe when available?", default=current.ypipe_enabled)
        enable_free = current.freellmapi_enabled if yes else typer.confirm(
            "Enable FreeLLMAPI when available?", default=current.freellmapi_enabled
        )
        enable_omni = current.omniroute_enabled if yes else typer.confirm(
            "Enable OmniRoute when available?", default=current.omniroute_enabled
        )

        if policy == "local-only":
            enable_free = False
            enable_omni = False

        settings = ExecutionSettings(
            policy=policy,
            ypipe_enabled=enable_ypipe,
            ypipe_url=ypipe_url,
            freellmapi_enabled=enable_free,
            freellmapi_url=free_url,
            freellmapi_api_key=effective_free_token,
            omniroute_enabled=enable_omni,
            omniroute_url=omni_url,
        )
        path = save_execution_settings(settings)

        final_free = _probe(FreeLLMAPIFabric) if enable_free else FabricHealth("DISABLED", False, "Disabled by setup policy.")
        final_ypipe = _probe(YpipeFabric) if enable_ypipe else FabricHealth("DISABLED", False, "Disabled by setup policy.")
        final_omni = _probe(OmniRouteFabric) if enable_omni else FabricHealth("DISABLED", False, "Disabled by setup policy.")
        final_ruflo = RufloOrchestrator().health()

        console.print("\n[bold]Saved configuration[/bold]")
        console.print(f"Policy: [cyan]{policy}[/cyan]")
        console.print(f"Config: {path}")
        console.print(f"Ypipe: {final_ypipe.status}")
        if _free_needs_credentials(final_free):
            console.print("FreeLLMAPI: ACTION_REQUIRED (router running; configure provider key + unified API key)")
        else:
            console.print(f"FreeLLMAPI: {final_free.status}")
        console.print(f"OmniRoute: {final_omni.status}")
        console.print(f"Ruflo orchestration: {'READY ' + (final_ruflo.version or '') if final_ruflo.ready else 'UNAVAILABLE'}")

        if policy == "local-only" and not final_ypipe.ready:
            console.print(
                "[red]Local-only was selected but Ypipe is not ready. "
                "Everstate will fail closed rather than use remote execution.[/red]"
            )
            raise typer.Exit(code=2)

        if not any(health.ready for health in (final_ypipe, final_free, final_omni)):
            if _free_needs_credentials(final_free):
                console.print(
                    "[yellow]No execution fabric is ready yet. FreeLLMAPI is installed and reachable but needs credentials. "
                    "Configure provider keys in its local dashboard and save the unified API key in Everstate.[/yellow]"
                )
            else:
                console.print("[yellow]Configuration was saved, but no execution fabric is ready yet.[/yellow]")
            raise typer.Exit(code=2)

        if not final_ruflo.ready:
            console.print(
                "[yellow]Ruflo v3 is not ready; AgentCouncil will use the native orchestrator until claude-flow v3 is installed.[/yellow]"
            )
        console.print("[green]Everstate execution setup is ready.[/green]")
