from __future__ import annotations

import asyncio
import json
import queue as qmod
import re
import threading
import urllib.error
import urllib.request
import uuid
from typing import AsyncIterator, Optional

from jarvis.core.events import CancelToken, CancelledError
from jarvis.core.types import LLMResponse, Message, ToolCall, ToolSpec
from jarvis.llm.base import LLMProvider, parse_tool_calls

_TOOL_NAME_SAFE = re.compile(r"[^a-zA-Z0-9_-]")
_THINK = re.compile(r"<think>.*?</think>|<think>.*$|</think>", re.DOTALL | re.IGNORECASE)


def _strip_think(text: str) -> str:
    """Remove leaked reasoning (`<think>...</think>`) from a model reply."""
    if not text:
        return text
    return _THINK.sub("", text).strip()


class _ThinkStripper:
    """Stateful `<think>` filter that tolerates tags split across stream deltas."""

    def __init__(self) -> None:
        self._in = False
        self._buf = ""

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        out: list[str] = []
        while self._buf:
            if self._in:
                i = self._buf.find("</think>")
                if i == -1:
                    self._buf = self._buf[-8:]
                    break
                self._buf = self._buf[i + len("</think>"):]
                self._in = False
                continue
            i = self._buf.find("<think>")
            if i == -1:
                keep = 6
                if len(self._buf) > keep:
                    out.append(self._buf[:-keep])
                    self._buf = self._buf[-keep:]
                break
            out.append(self._buf[:i])
            self._buf = self._buf[i + len("<think>"):]
            self._in = True
        return "".join(out)

    def flush(self) -> str:
        tail = "" if self._in else self._buf
        self._buf = ""
        self._in = False
        return tail


def sanitize_tool_name(name: str) -> str:
    """OpenAI-compatible function names must match ^[a-zA-Z0-9_-]+$."""
    safe = _TOOL_NAME_SAFE.sub("_", name) or "tool"
    return safe[:64]


def build_tool_name_map(tools: list[ToolSpec]) -> dict[str, str]:
    """Deterministic internal-name -> provider-safe-name map (collision-free)."""
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for tool in sorted(tools, key=lambda t: t.name):
        safe = sanitize_tool_name(tool.name)
        while safe in used:
            safe = (safe + "_")[:64]
        used.add(safe)
        mapping[tool.name] = safe
    return mapping


def messages_to_openai(messages: list[Message], name_map: Optional[dict[str, str]] = None) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content or ""})
            continue
        item: dict = {"role": m.role, "content": m.content or ""}
        if m.tool_calls:
            item["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {
                        "name": (name_map or {}).get(c.name, sanitize_tool_name(c.name)),
                        "arguments": json.dumps(c.arguments),
                    },
                }
                for c in m.tool_calls
            ]
        out.append(item)
    return out


def tools_to_openai(tools: list[ToolSpec], name_map: Optional[dict[str, str]] = None, *, strict: bool = False) -> list[dict]:
    out = []
    for t in tools:
        fn = {
            "name": (name_map or {}).get(t.name, sanitize_tool_name(t.name)),
            "description": t.description,
            "parameters": t.input_schema or {"type": "object", "properties": {}},
        }
        if strict:
            fn["strict"] = True
        out.append({"type": "function", "function": fn})
    return out


class OpenAICompatProvider(LLMProvider):
    """Any OpenAI-compatible /chat/completions endpoint.

    Works with: Ollama (http://localhost:11434/v1), LM Studio, llama.cpp
    `llama-server`, vLLM, LiteLLM, OpenRouter, DeepSeek, and the OpenAI/Anthropic
    gateways. Pure-stdlib transport so there are no hard dependencies.

    `extra_params` are merged into the request body — used for provider-specific
    knobs such as DeepSeek's ``{"thinking": {"type": "disabled"}}``.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str = "",
        timeout: float = 120.0,
        name: str | None = None,
        extra_params: Optional[dict] = None,
        reasoning_effort: Optional[str] = None,
        strict_tools: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.name = name or f"openai-compat:{model}"
        self.extra_params = dict(extra_params or {})
        self.reasoning_effort = reasoning_effort
        self.strict_tools = strict_tools
        self._last_tool_calls: list[ToolCall] = []

    def supports_streaming(self) -> bool:
        return True

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        temperature: float,
        max_tokens: int,
        *,
        stream: bool,
    ) -> dict:
        name_map = build_tool_name_map(tools) if tools else {}
        payload: dict = {
            "model": self.model,
            "messages": messages_to_openai(messages, name_map),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if tools:
            payload["tools"] = tools_to_openai(tools, name_map, strict=self.strict_tools)
            payload["tool_choice"] = "auto"
        # Provider-specific params (e.g. DeepSeek thinking toggle) are merged last.
        payload.update(self.extra_params)
        return payload

    def _post(self, payload: dict, cancel: Optional[CancelToken]) -> dict:
        if cancel and cancel.cancelled:
            raise CancelledError()
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=data, headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"LLM HTTP {e.code}: {body[:500]}") from e

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        cancel: Optional[CancelToken] = None,
    ) -> LLMResponse:
        name_map = build_tool_name_map(tools) if tools else {}
        decoder = {v: k for k, v in name_map.items()}
        payload = self._payload(messages, tools, temperature, max_tokens, stream=False)

        task = asyncio.create_task(asyncio.to_thread(self._post, payload, cancel))
        if cancel:
            unsub = cancel.on_cancel(task.cancel)
            try:
                result = await task
            finally:
                unsub()
        else:
            result = await task

        choices = result.get("choices") or []
        if not choices:
            raise RuntimeError(f"LLM returned no choices: {json.dumps(result)[:500]}")
        message = choices[0].get("message", {}) or {}
        return LLMResponse(
            text=_strip_think(message.get("content") or ""),
            tool_calls=parse_tool_calls(message.get("tool_calls") or [], name_decoder=decoder),
            finish_reason=choices[0].get("finish_reason", "stop"),
            usage=result.get("usage") or {},
            model=result.get("model", self.model),
        )

    def _sse_worker(self, payload: dict, q: "qmod.Queue", cancel: Optional[CancelToken]) -> None:
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions", data=data, headers=self._headers(), method="POST"
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for raw in resp:
                    if cancel and cancel.cancelled:
                        break
                    line = raw.decode("utf-8", "replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        break
                    q.put(("data", body))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            q.put(("err", f"LLM HTTP {e.code}: {body[:400]}"))
        except Exception as e:  # noqa: BLE001
            q.put(("err", f"{type(e).__name__}: {e}"))
        finally:
            q.put(None)

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        cancel: Optional[CancelToken] = None,
    ) -> AsyncIterator[str]:
        payload = self._payload(messages, tools, temperature, max_tokens, stream=True)
        name_map = build_tool_name_map(tools) if tools else {}
        decoder = {v: k for k, v in name_map.items()}
        q: "qmod.Queue" = qmod.Queue()
        self._last_tool_calls = []
        threading.Thread(target=self._sse_worker, args=(payload, q, cancel), daemon=True).start()

        fragments: dict[int, dict] = {}
        stripper = _ThinkStripper()
        while True:
            item = await asyncio.to_thread(q.get)
            if item is None:
                break
            kind, body = item
            if kind == "err":
                raise RuntimeError(body)
            try:
                obj = json.loads(body)
            except json.JSONDecodeError:
                continue
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                cleaned = stripper.feed(content)
                if cleaned:
                    yield cleaned
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = fragments.setdefault(idx, {"id": "", "name": "", "args": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["args"] += fn["arguments"]

        tail = stripper.flush()
        if tail:
            yield tail

        calls: list[ToolCall] = []
        for idx in sorted(fragments):
            slot = fragments[idx]
            if not slot["name"]:
                continue
            try:
                args = json.loads(slot["args"]) if slot["args"].strip() else {}
            except json.JSONDecodeError:
                args = {"_raw": slot["args"]}
            calls.append(
                ToolCall(
                    id=slot["id"] or f"call_{uuid.uuid4().hex[:8]}",
                    name=decoder.get(slot["name"], slot["name"]),
                    arguments=args,
                )
            )
        self._last_tool_calls = calls

    def parse_output(self, raw: str, tools: list[ToolSpec]) -> LLMResponse:
        calls = list(self._last_tool_calls)
        return LLMResponse(
            text=raw.strip(),
            tool_calls=calls,
            finish_reason="tool_calls" if calls else "stop",
            model=self.model,
        )
