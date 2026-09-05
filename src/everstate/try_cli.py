from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from .session_transfer import build_session_transfer_review
from .test_transfer import create_test_transfer_bundle
from .transfer_cli import (
    _parse_source,
    _prompt_destination,
    _prompt_session_or_projects,
    _prompt_source,
    _store,
)
from .transfer_plan import build_transfer_plan

app = typer.Typer(help="Try Everstate safely with one project and no provider launch.", invoke_without_command=True)
console = Console()


@app.callback(invoke_without_command=True)
def try_transfer(
    source: str | None = typer.Option(None, "--from", help="Source AI environment."),
    destination: str | None = typer.Option(None, "--to", help="Destination AI environment or provider key."),
    project: str | None = typer.Option(None, "--project", help="One project id, name, or root path."),
    session: str | None = typer.Option(None, "--session", help="Exact discovered Codex or Claude Code session id."),
    output_root: Path | None = typer.Option(None, "--output-root", file_okay=False, help="Optional test-bundle directory."),
) -> None:
    """Create an isolated continuation bundle without modifying canonical state or launching an AI."""
    store = _store()
    try:
        resolved_source = _parse_source(source) if source is not None else _prompt_source()

        if session is None and project is None:
            session, selected, all_projects, _ = _prompt_session_or_projects(store, resolved_source)
            if all_projects or len(selected) > 1:
                raise ValueError("Try mode supports exactly one project; choose one project for a safe test")
            project = selected[0] if selected else None

        resolved_destination = destination or _prompt_destination()

        if session is not None:
            review = build_session_transfer_review(
                store,
                source=resolved_source,
                destination=resolved_destination,
                session_id=session,
                project_selector=project,
            )
            selected_project = review.plan.projects[0]
            console.print(review.summary())
            console.print(f"Association evidence: {review.association_detail}")
        else:
            if project is None:
                raise ValueError("Try mode requires exactly one project")
            plan = build_transfer_plan(
                store,
                source=resolved_source,
                destination=resolved_destination,
                project_selectors=[project],
            )
            if len(plan.projects) != 1:
                raise ValueError("Try mode requires exactly one project")
            selected_project = plan.projects[0]
            console.print(plan.summary())

        bundle = create_test_transfer_bundle(
            store,
            project=selected_project,
            source=resolved_source,
            destination=resolved_destination,
            session_id=session,
            output_root=output_root,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    console.print("[bold green]TEST_TRANSFER_READY[/bold green]")
    console.print(f"State version: {bundle.state_version}")
    console.print(f"Bundle: {bundle.directory}")
    console.print(f"Review metadata: {bundle.metadata_path}")
    console.print(f"Continuation Markdown: {bundle.markdown_path}")
    console.print(f"Continuation JSON: {bundle.json_path}")
    console.print("[dim]No provider was launched. Canonical state was not refreshed or mutated.[/dim]")


if __name__ == "__main__":
    app()
