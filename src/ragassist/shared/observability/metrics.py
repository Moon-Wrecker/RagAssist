"""Prometheus metrics instrumentation and request timing middleware for RagAssist.

Consulted References & Standards:
- Prometheus Exposition Formats specification v0.0.4:
  https://prometheus.io/docs/instrumenting/exposition_formats/#text-based-format
- Starlette Middleware Architecture (ASGI timing and header injection):
  https://www.starlette.io/middleware/
- Python time.perf_counter() precision timing guidelines (PEP 418).
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp, Receive, Scope, Send


def _escape_label(value: str) -> str:
    """Prometheus text format 0.0.4: escape backslash, double quote and line feed inside a label value."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


_KNOWN_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


class SimplePrometheusRegistry:
    """Thread-safe in-memory Prometheus metric collector matching Prometheus 0.0.4 format."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(lambda: defaultdict(float))
        # name -> [observation count, running sum]: constant memory however many requests arrive.
        self._histograms: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        self._gauges: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(lambda: defaultdict(float))
        self._help: dict[str, str] = {}
        self._types: dict[str, str] = {}

    def register(self, name: str, metric_type: str, help_text: str) -> None:
        self._types[name] = metric_type
        self._help[name] = help_text

    def increment_counter(self, name: str, value: float = 1.0, **labels: str) -> None:
        label_tuple = tuple(sorted(labels.items()))
        self._counters[name][label_tuple] += value

    def observe_histogram(self, name: str, value: float) -> None:
        series = self._histograms[name]
        series[0] += 1.0
        series[1] += value

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        label_tuple = tuple(sorted(labels.items()))
        self._gauges[name][label_tuple] = value

    def format_labels(self, labels: tuple[tuple[str, str], ...]) -> str:
        if not labels:
            return ""
        pairs = [f'{k}="{_escape_label(v)}"' for k, v in labels]
        return "{" + ",".join(pairs) + "}"

    def export_text(self) -> str:
        """Render all collected metrics in standard Prometheus text format."""
        lines: list[str] = []

        # Export counters
        for name, series in self._counters.items():
            help_str = self._help.get(name, f"Help for {name}")
            t = self._types.get(name, "counter")
            lines.append(f"# HELP {name} {help_str}")
            lines.append(f"# TYPE {name} {t}")
            for labels, val in sorted(series.items()):
                lines.append(f"{name}{self.format_labels(labels)} {val}")

        # Export gauges
        for name, series in self._gauges.items():
            help_str = self._help.get(name, f"Help for {name}")
            t = self._types.get(name, "gauge")
            lines.append(f"# HELP {name} {help_str}")
            lines.append(f"# TYPE {name} {t}")
            for labels, val in sorted(series.items()):
                lines.append(f"{name}{self.format_labels(labels)} {val}")

        # Export histograms (count and sum)
        for name, values in self._histograms.items():
            help_str = self._help.get(name, f"Help for {name}")
            lines.append(f"# HELP {name} {help_str}")
            lines.append(f"# TYPE {name} histogram")
            count = int(values[0])
            val_sum = values[1]
            lines.append(f"{name}_count {count}")
            lines.append(f"{name}_sum {val_sum:.6f}")

        return "\n".join(lines) + "\n"


_global_registry = SimplePrometheusRegistry()
_global_registry.register("http_requests_total", "counter", "Total count of HTTP requests processed")
_global_registry.register("http_request_duration_seconds", "histogram", "Histogram of HTTP request durations in seconds")
_global_registry.register("ragassist_active_requests", "gauge", "Number of currently active HTTP requests")


def get_metrics_registry() -> SimplePrometheusRegistry:
    return _global_registry


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Calculates request latency, appends X-Process-Time, and records metrics."""

    def __init__(self, app: ASGIApp, registry: SimplePrometheusRegistry | None = None) -> None:
        super().__init__(app)
        self.registry = registry or _global_registry

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        method = request.method if request.method in _KNOWN_METHODS else "OTHER"

        self.registry.set_gauge("ragassist_active_requests", 1.0)
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
        except Exception:
            status_code = "500"
            raise
        finally:
            # The matched route template (``/v1/documents/{document_id}``), never the raw path: the raw path is
            # attacker-chosen, so it would make the number of series unbounded and leak identifiers.
            route = request.scope.get("route")
            path = getattr(route, "path", None) or "unmatched"
            duration = time.perf_counter() - start_time
            self.registry.set_gauge("ragassist_active_requests", 0.0)
            self.registry.increment_counter(
                "http_requests_total",
                1.0,
                method=method,
                handler=path,
                status=status_code,
            )
            self.registry.observe_histogram("http_request_duration_seconds", duration)

        response.headers["X-Process-Time"] = f"{duration:.4f}"
        return response


def setup_observability(app: FastAPI) -> None:
    """Wire request timing middleware and Prometheus metrics endpoint into FastAPI."""
    from fastapi import Depends
    from ragassist.shared.security.deps import get_current_principal
    from ragassist.shared.security.jwt import Principal

    app.add_middleware(RequestTimingMiddleware)

    @app.get("/metrics", tags=["Observability"], response_model=None)
    async def metrics_endpoint(principal: Principal = Depends(get_current_principal)) -> Response:
        """Expose Prometheus metrics in text format (administrators only: it is process-wide telemetry)."""
        from fastapi import HTTPException

        from ragassist.shared.security.jwt import UserRole

        if principal.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Administrator role required")
        content = _global_registry.export_text()
        return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")
