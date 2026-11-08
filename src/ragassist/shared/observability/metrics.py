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


class SimplePrometheusRegistry:
    """Thread-safe in-memory Prometheus metric collector matching Prometheus 0.0.4 format."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: dict[str, list[float]] = defaultdict(list)
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
        self._histograms[name].append(value)

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        label_tuple = tuple(sorted(labels.items()))
        self._gauges[name][label_tuple] = value

    def format_labels(self, labels: tuple[tuple[str, str], ...]) -> str:
        if not labels:
            return ""
        pairs = [f'{k}="{v}"' for k, v in labels]
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
            count = len(values)
            val_sum = sum(values) if values else 0.0
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
        method = request.method
        path = request.url.path

        self.registry.set_gauge("ragassist_active_requests", 1.0)
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
        except Exception:
            status_code = "500"
            raise
        finally:
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
    app.add_middleware(RequestTimingMiddleware)

    @app.get("/metrics", tags=["Observability"], response_model=None)
    async def metrics_endpoint() -> Response:
        """Expose Prometheus metrics in text format."""
        content = _global_registry.export_text()
        return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")
