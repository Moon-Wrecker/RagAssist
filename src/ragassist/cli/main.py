"""Command Line Interface for RagAssist service operations and background workers.

Consulted References:
- Typer Documentation: https://typer.tiangolo.com/
- Uvicorn programmatic execution: https://www.uvicorn.org/
"""

from __future__ import annotations

import asyncio
from typing import Any
import typer
import uvicorn

from ragassist.shared.config.settings import get_settings

app = typer.Typer(
    name="ragassist",
    help="RagAssist CLI: Production Multi-Tenant RAG Assistant",
    no_args_is_help=True,
)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host interface"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port number"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload on code change"),
) -> None:
    """Run the production FastAPI HTTP & SSE application server."""
    settings = get_settings()
    uvicorn.run(
        "ragassist.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=settings.LOG_LEVEL.lower(),
    )


@app.command("init-env")
def init_env(
    output: str = typer.Option(".env", "--output", "-o", help="File to create"),
    template: str = typer.Option(".env.example", "--template", help="Template to start from"),
    force: bool = typer.Option(False, "--force", help="Overwrite the file if it already exists"),
) -> None:
    """Create a working .env from the template, generating the secrets it leaves blank."""
    from pathlib import Path

    from ragassist.shared.config.envfile import write_env

    try:
        generated = write_env(Path(template), Path(output), force=force)
    except FileExistsError as exc:
        typer.echo(f"{exc} Use --force to replace it.", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Wrote {output}. Generated: {', '.join(generated) or 'nothing (no blank secrets)'}.")
    typer.echo("Set OPENAI_API_KEY (or OPENAI_COMPATIBLE_*) in it before using the assistant.")


@app.command()
def worker() -> None:
    """Run the background SQS ingestion worker."""
    from ragassist.worker.main import main as run_worker

    asyncio.run(run_worker())


if __name__ == "__main__":
    app()
