"""Chat model double for adapters that call ``with_structured_output(Schema)``.

``answers`` maps a schema class name to the field values to return, e.g.
``{"StructuredChoice": {"choice": "saas_action", "confidence": 0.93}}``.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda

from fakes.chat_model import ScriptedChatModel


class StructuredFakeModel(ScriptedChatModel):
    answers: dict[str, dict[str, Any]] = {}

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:  # type: ignore[override]
        name = getattr(schema, "__name__", str(schema))
        if name not in self.answers:
            raise AssertionError(f"StructuredFakeModel has no answer for schema {name!r}")

        async def _produce(_: Any) -> Any:
            self.calls.append([])
            return schema(**self.answers[name])

        return RunnableLambda(_produce)
