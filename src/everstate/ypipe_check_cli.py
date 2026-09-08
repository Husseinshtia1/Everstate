from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel

from .ypipe_fabric import YpipeConfig, YpipeError, YpipeFabric, YpipeMcpClient

console = Console()


def register(app: typer.Typer) -> None:
    @app.command("ypipe-check")
    def ypipe_check(
        json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable report."),
        check_mcp: bool = typer.Option(False, "--mcp", help="Initialize/list tools on EVERSTATE_YPIPE_MCP_URL."),
        inference: bool = typer.Option(False, "--inference", help="Run one minimal local inference after model discovery."),
        model: str | None = typer.Option(None, "--model", help="Specific local model for --inference; defaults to first discovered model."),
    ) -> None:
        """Check only Ypipe local execution surfaces; never contact cloud providers."""
        config = YpipeConfig.from_env()
        try:
            fabric = YpipeFabric(config)
            targets = fabric.discover_targets()
            health = fabric.health()
            mcp_report: dict | None = None
            inference_report: dict | None = None

            if check_mcp:
                if not config.mcp_url:
                    raise typer.BadParameter("Set EVERSTATE_YPIPE_MCP_URL before using --mcp", param_hint="--mcp")
                client = YpipeMcpClient(
                    config.mcp_url,
                    timeout=config.timeout,
                    allow_remote=config.allow_remote,
                )
                initialized = client.initialize()
                tools = client.list_tools()
                mcp_report = {
                    "ready": True,
                    "protocol_version": initialized.get("protocolVersion"),
                    "tool_count": len(tools),
                    "tools": [tool.get("name") for tool in tools if isinstance(tool.get("name"), str)],
                }

            if inference:
                selected = model or (targets[0].id if targets else None)
                if selected is None:
                    raise YpipeError("Cannot run inference because Ypipe reported no local models")
                if model and model not in {target.id for target in targets}:
                    raise typer.BadParameter(f"Configured model {model!r} is not in Ypipe's live model catalog", param_hint="--model")
                response = fabric.execute(
                    model=selected,
                    messages=[{"role": "user", "content": "Reply only EVERSTATE_YPIPE_READY."}],
                )
                inference_report = {
                    "ready": response.content.strip() == "EVERSTATE_YPIPE_READY",
                    "model": selected,
                    "response": response.content,
                }

            report = {
                "key": "ypipe",
                "state": health.status,
                "ready": health.ready,
                "detail": health.detail,
                "base_url": config.base_url,
                "allow_remote": config.allow_remote,
                "model_count": len(targets),
                "models": [target.id for target in targets],
                "mcp": mcp_report,
                "inference": inference_report,
            }
        except YpipeError as exc:
            report = {
                "key": "ypipe",
                "state": "UNAVAILABLE",
                "ready": False,
                "detail": str(exc),
                "base_url": config.base_url,
                "allow_remote": config.allow_remote,
                "model_count": 0,
                "models": [],
                "mcp": None,
                "inference": None,
            }

        if json_output:
            console.print_json(json.dumps(report))
        else:
            console.print(
                Panel.fit(
                    f"State: {report['state']}\n"
                    f"Ready: {report['ready']}\n"
                    f"Models: {report['model_count']}\n"
                    f"Local-only guard: {not report['allow_remote']}\n"
                    f"Detail: {report['detail']}",
                    title="Everstate Ypipe check",
                )
            )

        inference_result = report.get("inference")
        if not report["ready"] or (inference_result is not None and not inference_result["ready"]):
            raise typer.Exit(code=2)
