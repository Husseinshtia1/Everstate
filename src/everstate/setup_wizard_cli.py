from __future__ import annotations

import shutil
import subprocess
import webbrowser
from dataclasses import replace

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .execution_config import ExecutionSettings, save_execution_settings
from .freellmapi_fabric import FreeLLMAPIConfig, FreeLLMAPIFabric
from .omniroute_fabric import OmniRouteConfig, OmniRouteFabric
from .provider_fabric import FabricHealth
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


def _policy_prompt(default: str = "auto") -> str:
    console.print("\n[bold]Execution policy[/bold]")
    console.print("  [cyan]1[/cyan] Automatic (recommended): local → free remote → cloud")
    console.print("  [cyan]2[/cyan] Local only: never send project state to remote providers")
    console.print("  [cyan]3[/cyan] Cloud preferred: OmniRoute → FreeLLMAPI → local")
    choice = typer.prompt("Choose", default={"auto": "1", "local-only": "2", "cloud-preferred": "3"}.get(default, "1"))
    return {"1": "auto", "2": "local-only", "3": "cloud-preferred"}.get(choice.strip(), "auto")


def register(app: typer.Typer) -> None:
    @app.command("setup")
    def setup(
        yes: bool = typer.Option(False, "--yes", "-y", help="Accept recommended choices without interactive prompts."),
        install_missing: bool = typer.Option(False, "--install-missing", help="Install FreeLLMAPI automatically when missing."),
        freellmapi_token: str | None = typer.Option(None, "--freellmapi-token", help="Unified FreeLLMAPI token; stored in the 0600 Everstate execution config."),
        no_browser: bool = typer.Option(False, "--no-browser", help="Do not open the FreeLLMAPI dashboard when a token/provider setup is needed."),
    ) -> None:
        """Discover, configure, and validate Everstate execution fabrics interactively."""
        console.print(Panel.fit("Automatic execution discovery and configuration", title="Everstate Setup"))

        ypipe_url = YpipeConfig.base_url
        free_url = FreeLLMAPIConfig.base_url
        omni_url = OmniRouteConfig.base_url

        ypipe_health = _probe(lambda: YpipeFabric(YpipeConfig(base_url=ypipe_url)))
        free_health = _probe(lambda: FreeLLMAPIFabric(FreeLLMAPIConfig(base_url=free_url, api_key=freellmapi_token)))
        omni_health = _probe(lambda: OmniRouteFabric(OmniRouteConfig(base_url=omni_url)))

        table = Table(title="Detected execution fabrics")
        table.add_column("Fabric")
        table.add_column("Role")
        table.add_column("State")
        table.add_column("Ready")
        table.add_row("Ypipe", "LOCAL_SOVEREIGN", ypipe_health.status, str(ypipe_health.ready))
        table.add_row("FreeLLMAPI", "FREE_REMOTE", free_health.status, str(free_health.ready))
        table.add_row("OmniRoute", "REMOTE_MULTI_PROVIDER", omni_health.status, str(omni_health.ready))
        console.print(table)

        if not free_health.ready:
            should_install = install_missing or (not yes and typer.confirm("FreeLLMAPI is not ready. Install/configure it automatically?", default=True))
            if should_install:
                installed, detail = _install_freellmapi()
                console.print(f"[{'green' if installed else 'yellow'}]{detail}[/]")
                if installed:
                    free_health = _probe(lambda: FreeLLMAPIFabric(FreeLLMAPIConfig(base_url=free_url, api_key=freellmapi_token)))

        if not free_health.ready and "401" in free_health.detail:
            if freellmapi_token is None and not yes:
                if not no_browser:
                    webbrowser.open("http://127.0.0.1:3001")
                console.print("FreeLLMAPI is running but requires its unified token. Add provider keys in the local dashboard, then copy the unified token.")
                freellmapi_token = typer.prompt("FreeLLMAPI unified token", hide_input=True).strip() or None
                free_health = _probe(lambda: FreeLLMAPIFabric(FreeLLMAPIConfig(base_url=free_url, api_key=freellmapi_token)))

        policy = "auto" if yes else _policy_prompt()
        enable_ypipe = ypipe_health.ready if yes else typer.confirm("Enable Ypipe when available?", default=True)
        enable_free = free_health.ready if yes else typer.confirm("Enable FreeLLMAPI when available?", default=True)
        enable_omni = omni_health.ready if yes else typer.confirm("Enable OmniRoute when available?", default=True)

        if policy == "local-only":
            enable_free = False
            enable_omni = False

        settings = ExecutionSettings(
            policy=policy,
            ypipe_enabled=enable_ypipe,
            ypipe_url=ypipe_url,
            freellmapi_enabled=enable_free,
            freellmapi_url=free_url,
            freellmapi_api_key=freellmapi_token,
            omniroute_enabled=enable_omni,
            omniroute_url=omni_url,
        )
        path = save_execution_settings(settings)

        # Re-probe from exactly what was persisted so setup cannot claim success
        # based on transient values different from future Everstate runs.
        final_free = _probe(FreeLLMAPIFabric) if enable_free else FabricHealth("DISABLED", False, "Disabled by setup policy.")
        final_ypipe = _probe(YpipeFabric) if enable_ypipe else FabricHealth("DISABLED", False, "Disabled by setup policy.")
        final_omni = _probe(OmniRouteFabric) if enable_omni else FabricHealth("DISABLED", False, "Disabled by setup policy.")

        console.print("\n[bold]Saved configuration[/bold]")
        console.print(f"Policy: [cyan]{policy}[/cyan]")
        console.print(f"Config: {path}")
        console.print(f"Ypipe: {final_ypipe.status}")
        console.print(f"FreeLLMAPI: {final_free.status}")
        console.print(f"OmniRoute: {final_omni.status}")

        if policy == "local-only" and not final_ypipe.ready:
            console.print("[red]Local-only was selected but Ypipe is not ready. Everstate will fail closed rather than use remote execution.[/red]")
            raise typer.Exit(code=2)

        if not any(health.ready for health in (final_ypipe, final_free, final_omni)):
            console.print("[yellow]Configuration was saved, but no execution fabric is ready yet.[/yellow]")
            raise typer.Exit(code=2)

        console.print("[green]Everstate execution setup is ready.[/green]")
