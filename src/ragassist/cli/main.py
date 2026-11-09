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


@app.command()
def worker() -> None:
    """Run the background SQS ingestion worker."""
    from ragassist.worker.main import main as run_worker

    asyncio.run(run_worker())


if __name__ == "__main__":
    app()
