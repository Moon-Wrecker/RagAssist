"""Checkpoint serialisation for the assistant graph.

The graph state carries our own types (the verified ``Principal``, retrieved ``Hit`` rows). LangGraph's msgpack
serializer warns when it deserialises a type it was not told about and will refuse to in a future release, which
would make a paused approval impossible to resume. The allow-list below names exactly the types the state holds,
so resuming keeps working under ``LANGGRAPH_STRICT_MSGPACK`` and after the default flips.

Consulted: ``langgraph.checkpoint.serde.jsonplus.JsonPlusSerializer`` (``allowed_msgpack_modules``), LangGraph
persistence docs.
"""

from __future__ import annotations

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

#: ``(module, class)`` pairs the checkpoint may deserialise. Add a type here when it enters the graph state.
ALLOWED_MSGPACK_MODULES: tuple[tuple[str, str], ...] = (
    ("ragassist.shared.security.jwt", "Principal"),
    ("ragassist.shared.security.jwt", "UserRole"),
    ("ragassist.modules.retrieval.domain", "Hit"),
)


def checkpoint_serde() -> JsonPlusSerializer:
    """The serializer every checkpointer of the assistant graph must use."""
    return JsonPlusSerializer(allowed_msgpack_modules=list(ALLOWED_MSGPACK_MODULES))
