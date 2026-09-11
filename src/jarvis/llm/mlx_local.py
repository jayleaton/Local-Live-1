from __future__ import annotations

import asyncio
import queue as qmod
import re
import threading
import uuid
from typing import AsyncIterator, Optional

from jarvis.core.events import CancelToken, CancelledError
from jarvis.core.types import LLMResponse, Message, ToolCall, ToolSpec
from jarvis.llm.base import LLMProvider
from jarvis.llm.openai_compat import build_tool_name_map, sanitize_tool_name


def to_chat_messages(messages: list[Message], name_map: Optional[dict[str, str]] = None) -> list[dict]:
    """Convert our messages to a chat-template-friendly list, preserving tool calls."""
    out: list[dict] = []
    name_map = name_map or {}
    for m in messages:
        if m.role == "tool":
            item = {"role": "tool", "content": m.content or ""}
            if m.name:
                item["name"] = name_map.get(m.name, sanitize_tool_name(m.name))
            out.append(item)
        elif m.role == "assistant" and m.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": m.content or "",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": name_map.get(c.name, sanitize_tool_name(c.name)),
                                "arguments": c.arguments,
                            },
                        }
                        for c in m.tool_calls
                    ],
                }
            )
        else:
            out.append({"role": m.role, "content": m.content or ""})
    return out


class MLXProvider(LLMProvider):
    """In-process local inference via MLX on Apple Silicon (Metal).

    Supports native tool calling (MCP + worker agents) via the model's chat
    template and mlx-lm's tool parser. Thinking is disabled by default for
    low-latency voice replies.
    """

    def __init__(
        self,
        model_id: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 256,
        enable_thinking: bool = False,
        name: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enable_thinking = enable_thinking
        self.name = name or f"mlx:{model_id.split('/')[-1]}"
        self._model = None
        self._tokenizer = None

    def supports_tools(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return True

    def tool_markers(self) -> list[str]:
        return ["<tool_call", "<|tool_call"]

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        cancel: Optional[CancelToken] = None,
    ) -> AsyncIterator[str]:
        if cancel and cancel.cancelled:
            raise CancelledError()
        model, tokenizer, _schemas, _name_map, prompt = self._prepare(messages, tools)
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        sampler = make_sampler(temp=self.temperature, top_p=0.95)
        q: "qmod.Queue" = qmod.Queue()

        def worker() -> None:
            try:
                for resp in stream_generate(model, tokenizer, prompt, max_tokens=self.max_tokens, sampler=sampler):
                    if cancel and cancel.cancelled:
                        break
                    q.put(resp.text)
            except Exception as e:  # noqa: BLE001
                q.put(("__err__", f"{type(e).__name__}: {e}"))
            finally:
                q.put(None)

        threading.Thread(target=worker, daemon=True).start()
        while True:
            item = await asyncio.to_thread(q.get)
            if item is None:
                break
            if isinstance(item, tuple):
                raise RuntimeError(item[1])
            yield item

    def parse_output(self, raw: str, tools: list[ToolSpec]) -> LLMResponse:
        _model, tokenizer = self._load()
        name_map = build_tool_name_map(tools) if tools else {}
        decoder = {v: k for k, v in name_map.items()}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": name_map.get(t.name, sanitize_tool_name(t.name)),
                    "description": t.description,
                    "parameters": t.input_schema or {"type": "object", "properties": {}},
                },
            }
            for t in tools
        ]
        text, calls = self._split_tool_calls(raw, tokenizer, schemas, decoder)
        return LLMResponse(
            text=text,
            tool_calls=calls,
            finish_reason="tool_calls" if calls else "stop",
            model=self.model_id,
        )

    def _prepare(self, messages: list[Message], tools: list[ToolSpec]):
        model, tokenizer = self._load()
        name_map = build_tool_name_map(tools) if tools else {}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": name_map.get(t.name, sanitize_tool_name(t.name)),
                    "description": t.description,
                    "parameters": t.input_schema or {"type": "object", "properties": {}},
                },
            }
            for t in tools
        ]
        prompt = self._render_prompt(messages, schemas, name_map)
        return model, tokenizer, schemas, name_map, prompt

    def _load(self):
        if self._model is None:
            from mlx_lm import load

            self._model, self._tokenizer = load(self.model_id)
        return self._model, self._tokenizer

    def _render_prompt(self, messages: list[Message], schemas: list[dict], name_map: dict[str, str]) -> str:
        _model, tokenizer = self._load()
        chat = to_chat_messages(messages, name_map)
        kwargs: dict = {"add_generation_prompt": True, "tokenize": False}
        if schemas:
            kwargs["tools"] = schemas
            kwargs["enable_thinking"] = self.enable_thinking
        try:
            return tokenizer.apply_chat_template(chat, **kwargs)
        except TypeError:
            kwargs.pop("enable_thinking", None)
            return tokenizer.apply_chat_template(chat, **kwargs)

    def _generate_sync(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        cancel: Optional[CancelToken],
    ) -> LLMResponse:
        model, tokenizer = self._load()
        name_map = build_tool_name_map(tools) if tools else {}
        decoder = {v: k for k, v in name_map.items()}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": name_map.get(t.name, sanitize_tool_name(t.name)),
                    "description": t.description,
                    "parameters": t.input_schema or {"type": "object", "properties": {}},
                },
            }
            for t in tools
        ]
        prompt = self._render_prompt(messages, schemas, name_map)

        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        sampler = make_sampler(temp=self.temperature, top_p=0.95)
        parts: list[str] = []
        finish = "stop"
        for response in stream_generate(model, tokenizer, prompt, max_tokens=self.max_tokens, sampler=sampler):
            if cancel and cancel.cancelled:
                finish = "cancelled"
                break
            parts.append(response.text)
            if response.finish_reason:
                finish = response.finish_reason
        raw = "".join(parts)

        text, tool_calls = self._split_tool_calls(raw, tokenizer, schemas, decoder)
        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else finish,
            model=self.model_id,
        )

    @staticmethod
    def _split_tool_calls(
        raw: str,
        tokenizer,
        schemas: list[dict],
        decoder: dict[str, str],
    ) -> tuple[str, list[ToolCall]]:
        if not raw or not tokenizer.has_tool_calling:
            return raw.strip(), []
        start, end = tokenizer.tool_call_start, tokenizer.tool_call_end
        pattern = re.compile(re.escape(start) + "(.*?)" + re.escape(end), re.DOTALL)
        calls: list[ToolCall] = []
        text_parts: list[str] = []
        pos = 0
        for match in pattern.finditer(raw):
            text_parts.append(raw[pos : match.start()])
            body = match.group(1).strip()
            try:
                parsed = tokenizer.tool_parser(body, schemas)
            except Exception:
                parsed = None
            items = parsed if isinstance(parsed, list) else [parsed] if parsed else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("function", {}).get("name", "")
                args = item.get("arguments", item.get("parameters", {}))
                if isinstance(args, str):
                    import json

                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"_raw": args}
                calls.append(
                    ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=decoder.get(name, name), arguments=args or {})
                )
            pos = match.end()
        text_parts.append(raw[pos:])
        return "".join(text_parts).strip(), calls

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        cancel: Optional[CancelToken] = None,
    ) -> LLMResponse:
        if cancel and cancel.cancelled:
            raise CancelledError()
        result = await asyncio.to_thread(self._generate_sync, messages, tools, cancel)
        if cancel and cancel.cancelled:
            raise CancelledError()
        return result
