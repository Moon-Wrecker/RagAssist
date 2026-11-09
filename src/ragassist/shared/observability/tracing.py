"""Langfuse tracing for assistant turns.

Goal: every assistant turn is one readable trace: the user's question in, the answer out, the retrieval, model
calls, tools and approvals nested inside, grouped by conversation (session) and user.

Consulted (see docs/adr/0012-langfuse-tracing.md):
  * https://langfuse.com/docs/observability/best-practices : one trace per turn, verb-first stable names,
    meaningful root input/output, session/user/tags/metadata, environment.
  * https://langfuse.com/integrations/frameworks/langchain : the ``CallbackHandler`` captures LangGraph nodes,
    model calls (model name, usage) and tools, nested under the active observation.
  * https://langfuse.com/docs/observability/features/masking : ``mask_otel_spans`` redacts at export time.
  * https://langfuse.com/docs/observability/sdk/instrumentation : ``propagate_attributes``, flush/shutdown.

Design:
  * Disabled (the default) it costs nothing: no SDK import, no callbacks, ``turn()`` yields a null object.
  * Secrets never leave the process: the graph input carries the signed-in principal (including its bearer
    token), so every exported attribute is passed through :func:`redact` first.
  * Tenancy: ``user_id`` is the user's UUID, ``session_id`` the conversation id, and the tenant id travels as
    metadata, so a project can be filtered per tenant without the tenant becoming a high-cardinality tag.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, fields, is_dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

REDACTED = "[REDACTED]"

#: Keys whose value is a credential, whatever the value looks like (compared lower-case, with ``-`` as ``_``).
_SECRET_KEYS = frozenset(
    {
        "raw_token",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "bearer",
        "password",
        "passphrase",
        "secret",
        "secret_key",
        "client_secret",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "set_cookie",
        "x_api_key",
        "x_dev_auth_secret",
    }
)

#: Credential-shaped values that appear inside free text.
_SECRET_VALUE = re.compile(
    r"(?:eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"  # a JWT
    r"|(?i:bearer)\s+[A-Za-z0-9._~+/=-]{16,}"  # an Authorization header value
    r"|\b(?:sk|pk)-[A-Za-z0-9][A-Za-z0-9_-]{15,}"  # provider and Langfuse keys
    r"|\blsv2_[a-z]{2}_[A-Za-z0-9_]{16,}"  # LangSmith keys
    r"|\bAIza[A-Za-z0-9_-]{30,})"  # Google keys
)

#: Span attributes that hold user data; everything else (ids, names, types, model, usage) is left alone.
_DATA_ATTRIBUTE_PREFIX = "langfuse."


def _is_secret_key(key: object) -> bool:
    return str(key).lower().replace("-", "_") in _SECRET_KEYS


def redact(value: Any) -> Any:
    """Return ``value`` with credentials replaced by ``[REDACTED]`` (dicts, lists and strings, recursively)."""
    if isinstance(value, Mapping):
        return {k: (REDACTED if _is_secret_key(k) and v else redact(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _SECRET_VALUE.sub(REDACTED, value)
    if is_dataclass(value) and not isinstance(
        value, type
    ):  # e.g. the signed-in Principal, token included
        return redact({f.name: getattr(value, f.name) for f in fields(value)})
    dump = getattr(value, "model_dump", None)
    if callable(dump):  # a pydantic model
        return redact(dump())
    return value


def _redact_attribute(key: str, value: str) -> str:
    """Redact one exported span attribute. Values the SDK JSON-encodes are decoded, redacted and re-encoded."""
    if _is_secret_key(key.rsplit(".", 1)[-1]):
        return json.dumps(REDACTED)
    try:
        decoded = json.loads(value)
    except ValueError:
        return _SECRET_VALUE.sub(REDACTED, value)
    redacted = redact(decoded)
    return value if redacted == decoded else json.dumps(redacted, ensure_ascii=False)


def mask_otel_spans(*, params: Any) -> Any:
    """Langfuse export hook: redact credentials from every Langfuse attribute of every span in the batch."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    patches = {}
    for identifier, span in params.spans.items():
        changed = {
            key: new
            for key, value in span.attributes.items()
            if isinstance(value, str)
            and key.startswith(_DATA_ATTRIBUTE_PREFIX)
            and (new := _redact_attribute(key, value)) != value
        }
        if changed:
            patches[identifier] = OtelSpanPatch(set_attributes=changed)
    return MaskOtelSpansResult(span_patches=patches) if patches else None


@dataclass(frozen=True)
class TurnContext:
    """What identifies one traced turn. Plain values only, so callers need no tracing types."""

    name: str  # stable and verb-first: "answer-question", "decide-action"
    mode: str  # "stream", "json" or "approval"
    question: str
    conversation_id: str
    user_id: str
    tenant_id: str
    role: str


class TurnTrace:
    """The open root observation of a turn. ``config`` wires the graph run into it; ``finish`` sets its output."""

    def __init__(self, root: Any, handler_factory: Any) -> None:
        self._root = root
        self._handler_factory = handler_factory

    def config(self, base: dict[str, Any]) -> dict[str, Any]:
        """``base`` plus the Langfuse callback handler, which nests the graph under this turn's root."""
        return {
            **base,
            "callbacks": [*base.get("callbacks", []), self._handler_factory()],
            "run_name": "assistant-graph",
        }

    def finish(self, output: Any, **metadata: str) -> None:
        """Set the turn's output (the answer a reviewer reads) and small string facts such as route and status."""
        self._root.update(output=output, metadata={k: v for k, v in metadata.items() if v})


class _NullTurn:
    """Used when tracing is off: the graph config is untouched and nothing is recorded."""

    def config(self, base: dict[str, Any]) -> dict[str, Any]:
        return base

    def finish(self, output: Any, **metadata: str) -> None:
        return None


class Tracing:
    """Facade over the Langfuse client. ``Tracing(None)`` is the disabled, free implementation."""

    def __init__(self, client: Any | None = None, handler_factory: Any | None = None) -> None:
        self._client = client
        self._handler_factory = handler_factory

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @contextmanager
    def turn(self, ctx: TurnContext) -> Iterator[TurnTrace | _NullTurn]:
        """One trace per turn: a root observation with the question as input, attributes propagated to children."""
        if self._client is None:
            yield _NullTurn()
            return
        from langfuse import propagate_attributes

        with (
            self._client.start_as_current_observation(
                name=ctx.name, as_type="agent", input=ctx.question
            ) as root,
            propagate_attributes(
                trace_name=ctx.name,
                user_id=ctx.user_id,
                session_id=ctx.conversation_id,
                tags=["assistant", ctx.mode],
                metadata={"tenant_id": ctx.tenant_id, "role": ctx.role},
            ),
        ):
            yield TurnTrace(root, self._handler_factory)

    @contextmanager
    def observe(self, name: str, *, as_type: str, input: Any) -> Iterator[TurnTrace | _NullTurn]:
        """A typed child observation (e.g. ``retriever``) for work our own code does outside LangChain.

        Names stay stable and verb-first; dynamic values go in ``finish(..., key=value)`` metadata. Off, it is free.
        """
        if self._client is None:
            yield _NullTurn()
            return
        with self._client.start_as_current_observation(
            name=name, as_type=as_type, input=input
        ) as obs:
            yield TurnTrace(obs, self._handler_factory)

    def flush(self) -> None:
        if self._client is not None:
            self._client.flush()

    def shutdown(self) -> None:
        if self._client is not None:
            self._client.shutdown()


def configure_langsmith(settings: Any) -> bool:
    """Route LangChain's own LangSmith tracing through a client that redacts credentials first.

    LangSmith has no export hook like Langfuse's, but its client takes ``hide_inputs``, ``hide_outputs`` and
    ``hide_metadata``. Configuring that client globally means every LangChain run, including the graph input
    that carries the signed-in principal, is redacted before it leaves the process. Returns whether it is on.
    """
    import langsmith

    if not (settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY):
        langsmith.configure(enabled=False)
        return False
    client = langsmith.Client(
        api_key=settings.LANGSMITH_API_KEY,
        api_url=settings.LANGSMITH_ENDPOINT,
        hide_inputs=redact,
        hide_outputs=redact,
        hide_metadata=redact,
    )
    langsmith.configure(client=client, enabled=True, project_name=settings.LANGSMITH_PROJECT)
    logger.info("langsmith.enabled", project=settings.LANGSMITH_PROJECT)
    return True


_tracing: Tracing | None = None


def build_tracing(settings: Any) -> Tracing:
    """The tracing facade for ``settings``: enabled only when the flag is on and both keys are present."""
    if not settings.LANGFUSE_TRACING:
        return Tracing()
    if not (settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY):
        logger.warning(
            "tracing.disabled", reason="LANGFUSE_TRACING is on but a Langfuse key is missing"
        )
        return Tracing()
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler

    client = Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        base_url=settings.LANGFUSE_BASE_URL,
        environment=settings.APP_ENV,
        sample_rate=settings.LANGFUSE_SAMPLE_RATE,
        mask_otel_spans=mask_otel_spans,
    )
    logger.info(
        "tracing.enabled", base_url=settings.LANGFUSE_BASE_URL, environment=settings.APP_ENV
    )
    return Tracing(client, lambda: CallbackHandler(public_key=settings.LANGFUSE_PUBLIC_KEY))


def get_tracing() -> Tracing:
    """The process-wide tracing facade, built from settings on first use."""
    global _tracing
    if _tracing is None:
        from ragassist.shared.config.settings import get_settings

        _tracing = build_tracing(get_settings())
    return _tracing


def reset_tracing() -> None:
    """Forget the cached facade (tests, and a settings reload)."""
    global _tracing
    _tracing = None


async def shutdown_tracing() -> None:
    """Flush buffered traces and close the client; the flush blocks, so it runs off the event loop."""
    tracing, _ = _tracing, None
    if tracing is not None and tracing.enabled:
        await asyncio.to_thread(tracing.shutdown)
    reset_tracing()
