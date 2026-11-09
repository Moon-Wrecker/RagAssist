"""Scripted chat model: a real LangChain ``BaseChatModel`` that replays a fixed script.

Each element of ``script`` is consumed by one model call and may be:

* ``str``                 -> ``AIMessage(content=...)``
* ``BaseMessage``         -> returned as is (use :func:`tool_call_message` for tool calls)
* ``BaseException``       -> raised (simulates a provider outage / timeout)

Running past the end of the script fails loudly (an unexpected extra LLM call is a test bug) unless
``repeat_last=True``. Every call's input messages are recorded in ``calls``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field, PrivateAttr


def tool_call_message(name: str, args: dict[str, Any], call_id: str = "call_1") -> AIMessage:
    """An assistant message that requests one tool call."""
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


class ScriptedChatModel(BaseChatModel):
    script: list[Any] = Field(default_factory=list)
    repeat_last: bool = False
    label: str = "scripted"
    calls: list[list[BaseMessage]] = Field(default_factory=list)
    bound_tools: list[Any] = Field(default_factory=list)
    _cursor: int = PrivateAttr(default=0)

    @classmethod
    def from_script(cls, *script: Any, **kwargs: Any) -> ScriptedChatModel:
        return cls(script=list(script), **kwargs)

    # -- introspection helpers ------------------------------------------------------------------
    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def exhausted(self) -> bool:
        return self._cursor >= len(self.script)

    # -- BaseChatModel surface ------------------------------------------------------------------
    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> ScriptedChatModel:  # type: ignore[override]
        self.bound_tools.extend(tools)
        return self

    def _next(self) -> Any:
        if self._cursor < len(self.script):
            item = self.script[self._cursor]
        elif self.repeat_last and self.script:
            item = self.script[-1]
        else:
            raise AssertionError(
                f"ScriptedChatModel '{self.label}' called {self._cursor + 1} time(s) "
                f"but the script only has {len(self.script)} response(s)"
            )
        self._cursor += 1
        return item

    @staticmethod
    def _as_message(item: Any) -> BaseMessage:
        return item if isinstance(item, BaseMessage) else AIMessage(content=str(item))

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        item = self._next()
        if isinstance(item, BaseException):
            raise item
        return ChatResult(generations=[ChatGeneration(message=self._as_message(item))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop=stop, **kwargs)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        self.calls.append(list(messages))
        item = self._next()
        if isinstance(item, BaseException):
            raise item
        message = self._as_message(item)
        if getattr(message, "tool_calls", None):
            yield ChatGenerationChunk(
                message=AIMessageChunk(content=message.content, tool_calls=message.tool_calls)
            )
            return
        text = str(message.content)
        words = text.split(" ")
        for index, word in enumerate(words):
            token = word if index == len(words) - 1 else word + " "
            yield ChatGenerationChunk(message=AIMessageChunk(content=token))

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        for chunk in self._stream(messages, stop=stop, **kwargs):
            yield chunk
