from __future__ import annotations

from typing import Callable, Optional

from jarvis.core.events import CancelToken
from jarvis.core.types import LLMResponse, Message, ToolSpec
from jarvis.llm.base import LLMProvider

ScriptFn = Callable[[list[Message], list[ToolSpec]], LLMResponse]


class ScriptedProvider(LLMProvider):
    """Deterministic provider for tests and the eval harness.

    Given the full message list and tool specs, returns a scripted response.
    No model, no network — lets us test the harness, policy, and router exactly.
    """

    name = "scripted"

    def __init__(self, script: ScriptFn, *, name: str | None = None, supports_tools: bool = True) -> None:
        self._script = script
        self._supports_tools = supports_tools
        if name:
            self.name = name

    def supports_tools(self) -> bool:
        return self._supports_tools

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        cancel: Optional[CancelToken] = None,
    ) -> LLMResponse:
        if cancel:
            cancel.raise_if_cancelled()
        return self._script(messages, tools)


class EchoProvider(LLMProvider):
    """Trivial provider that echoes the last user message (no tools)."""

    name = "echo"

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        cancel: Optional[CancelToken] = None,
    ) -> LLMResponse:
        last = next((m for m in reversed(messages) if m.role == "user"), None)
        return LLMResponse(text=(last.content if last else "") or "", finish_reason="stop")
