"""Cache counters appear on /metrics with bounded labels (ADR 0015)."""

from __future__ import annotations

from support.settings import make_settings

from ragassist.platform.cache import build_cache_service, get_cache_service
from ragassist.platform.cache import keys as kinds
from ragassist.platform.cache.adapters.memory_adapter import InMemoryCache
from ragassist.platform.cache.metrics import install_cache_metrics
from ragassist.shared.observability.metrics import SimplePrometheusRegistry, get_metrics_registry

TENANT = "a0000000-0000-0000-0000-00000000000a"


async def test_hits_misses_evictions_and_size_are_exported() -> None:
    registry = SimplePrometheusRegistry()
    svc = build_cache_service(make_settings(), InMemoryCache(max_entries=2, max_value_bytes=1024))
    install_cache_metrics(svc, registry)

    for text in ("a", "b", "c"):  # three entries into a table of two: one eviction
        key = svc.keys.key(kinds.DECISION, TENANT, text=text)
        await svc.get_json(kinds.DECISION, key)  # miss
        await svc.set_json(kinds.DECISION, key, {"v": text}, 30)
    await svc.get_json(kinds.DECISION, svc.keys.key(kinds.DECISION, TENANT, text="c"))  # hit

    text = registry.export_text()
    assert 'ragassist_cache_requests_total{kind="dec",result="hit"} 1' in text
    assert 'ragassist_cache_requests_total{kind="dec",result="miss"} 3' in text
    assert 'ragassist_cache_evictions_total{backend="memory"} 1' in text
    assert 'ragassist_cache_entries{backend="memory"} 2' in text


async def test_no_tenant_or_key_ever_appears_as_a_label() -> None:
    registry = SimplePrometheusRegistry()
    svc = build_cache_service(make_settings(), InMemoryCache(max_entries=5, max_value_bytes=1024))
    install_cache_metrics(svc, registry)
    await svc.set_json(kinds.DECISION, svc.keys.key(kinds.DECISION, TENANT, text="secret"), 1, 30)
    await svc.get_json(kinds.DECISION, svc.keys.key(kinds.DECISION, TENANT, text="secret"))
    exported = registry.export_text()
    assert TENANT not in exported and "secret" not in exported


async def test_the_process_wide_service_is_exported_on_the_global_registry() -> None:
    svc = get_cache_service()
    await svc.get_json(kinds.DECISION, svc.keys.key(kinds.DECISION, TENANT, text="q"))
    assert "ragassist_cache_requests_total" in get_metrics_registry().export_text()
