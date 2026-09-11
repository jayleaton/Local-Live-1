from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from jarvis.core.events import CancelToken
from jarvis.core.types import LLMResponse, Message, ToolCall, ToolSpec


class LLMProvider(ABC):
    """Model-agnostic completion interface.

    Deliberately mirrors the OpenAI chat-completions tool-calling contract, so
    every local runtime (llama.cpp server, Ollama, LM Studio, vLLM, MLX server)
    and any cloud/gateway drops in behind the same seam.
    """

    name: str = "provider"

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        cancel: Optional[CancelToken] = None,
    ) -> LLMResponse:
        raise NotImplementedError

    def supports_tools(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return False

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        cancel: Optional[CancelToken] = None,
    ) -> AsyncIterator[str]:
        """Yield raw model output chunks. Default: one shot from complete()."""
        resp = await self.complete(messages, tools, temperature=temperature, max_tokens=max_tokens, cancel=cancel)
        if resp.text:
            yield resp.text

    def parse_output(self, raw: str, tools: list[ToolSpec]) -> LLMResponse:
        """Parse accumulated streamed text into text + tool calls."""
        return LLMResponse(text=raw)

    def tool_markers(self) -> list[str]:
        """Substrings that signal the start of a tool call in raw output."""
        return []


def parse_tool_calls(raw_calls: list[dict], name_decoder: Optional[dict[str, str]] = None) -> list[ToolCall]:
    """Normalize OpenAI-style tool_calls into our ToolCall type.

    `name_decoder` maps provider-safe function names back to internal names
    (e.g. "demo_add" -> "demo.add").
    """
    import json
    import uuid

    calls: list[ToolCall] = []
    for raw in raw_calls or []:
        fn = raw.get("function", raw)
        name = fn.get("name", "")
        if name_decoder:
            name = name_decoder.get(name, name)
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {"_raw": args}
        calls.append(ToolCall(id=raw.get("id") or f"call_{uuid.uuid4().hex[:8]}", name=name, arguments=args or {}))
    return calls
