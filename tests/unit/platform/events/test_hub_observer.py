"""EventHub observers see every dispatched event, whatever the audience, and cannot break delivery."""

from __future__ import annotations

from ragassist.platform.events import (
    Event,
    EventHub,
    Viewer,
    document_changed,
)

TENANT = "a0000000-0000-0000-0000-00000000000a"


async def test_observer_sees_events_no_stream_may_receive() -> None:
    hub = EventHub()
    seen: list[Event] = []
    hub.add_observer(seen.append)
    hub.dispatch(document_changed(TENANT, "d1"))  # admins only, and nobody is connected
    assert [e.type for e in seen] == ["document.changed"]


async def test_a_raising_observer_does_not_stop_delivery_or_other_observers() -> None:
    hub = EventHub()
    seen: list[Event] = []

    def broken(_: Event) -> None:
        raise RuntimeError("boom")

    hub.add_observer(broken)
    hub.add_observer(seen.append)
    with hub.subscribe(Viewer(TENANT, "u1", "admin")) as sub:
        hub.dispatch(document_changed(TENANT, "d1"))
        got = await sub.get(timeout=0.1)
    assert seen and got is not None
