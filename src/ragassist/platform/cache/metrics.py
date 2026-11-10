"""Cache counters on ``/metrics`` (ADR 0015): hits and misses per kind of entry, evictions, expirations, refused
values, backend errors and the number of live entries.

Labels are the kind of entry (a short fixed set) and the backend name, never a tenant or a key, so the number of
series stays constant however many tenants there are.
"""

from __future__ import annotations

from ragassist.platform.cache.service import CacheService
from ragassist.shared.observability.metrics import SimplePrometheusRegistry, get_metrics_registry

_HELP = {
    "ragassist_cache_requests_total": ("counter", "Cache lookups by kind of entry and result"),
    "ragassist_cache_evictions_total": ("counter", "Entries dropped to stay inside the size bound"),
    "ragassist_cache_expirations_total": ("counter", "Entries removed because their TTL passed"),
    "ragassist_cache_rejected_total": ("counter", "Values refused for exceeding the size limit"),
    "ragassist_cache_errors_total": ("counter", "Backend failures (treated as misses)"),
    "ragassist_cache_entries": ("gauge", "Live entries in the cache"),
}


def install_cache_metrics(service: CacheService, registry: SimplePrometheusRegistry | None = None) -> None:
    """Export ``service``'s counters; installing again (a rebuilt cache) replaces the previous collector."""
    reg = registry or get_metrics_registry()
    for name, (kind, text) in _HELP.items():
        reg.register(name, kind, text)

    def collect(r: SimplePrometheusRegistry) -> None:
        backend = service.backend
        for entry_kind, counts in service.counters().items():
            r.set_counter("ragassist_cache_requests_total", counts["hit"], kind=entry_kind, result="hit")
            r.set_counter("ragassist_cache_requests_total", counts["miss"], kind=entry_kind, result="miss")
        stats = service.stats()
        r.set_counter("ragassist_cache_evictions_total", stats.evictions, backend=backend)
        r.set_counter("ragassist_cache_expirations_total", stats.expirations, backend=backend)
        r.set_counter("ragassist_cache_rejected_total", stats.rejected, backend=backend)
        r.set_counter("ragassist_cache_errors_total", stats.errors, backend=backend)
        r.set_gauge("ragassist_cache_entries", stats.size, backend=backend)

    reg.add_collector("cache", collect)
