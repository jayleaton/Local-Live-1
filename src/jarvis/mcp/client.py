from __future__ import annotations

import asyncio
import itertools
import json
from typing import Any, Callable, Optional

from jarvis import __version__
from jarvis.core.events import CancelToken, CancelledError
from jarvis.core.types import ToolCall, ToolResult
from jarvis.mcp.transport import Transport, TransportError

DEFAULT_PROTOCOL_VERSION = "2026-07-28"


class MCPError(RuntimeError):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"MCP error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class MCPClient:
    """Minimal MCP client: initialize handshake, tools/list, tools/call, cancel.

    Implemented directly against the JSON-RPC wire format so the harness owns
    its own tool-calling semantics and has no hard SDK dependency.
    """

    def __init__(
        self,
        name: str,
        transport: Transport,
        *,
        protocol_version: str = DEFAULT_PROTOCOL_VERSION,
        request_timeout: float = 30.0,
        on_notification: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self.name = name
        self.transport = transport
        self.protocol_version = protocol_version
        self.request_timeout = request_timeout
        self.server_info: dict[str, Any] = {}
        self.server_capabilities: dict[str, Any] = {}
        self.on_notification = on_notification

        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._started = False
        self._closed = False

    async def start(self) -> None:
        await self.transport.start()
        self._reader_task = asyncio.create_task(self._read_loop())
        result = await self._request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "jarvis", "version": __version__},
            },
        )
        self.server_info = result.get("serverInfo", {})
        self.server_capabilities = result.get("capabilities", {})
        negotiated = result.get("protocolVersion")
        if negotiated:
            self.protocol_version = negotiated
        await self.transport.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._started = True

    async def _read_loop(self) -> None:
        while not self._closed:
            try:
                msg = await self.transport.receive()
            except TransportError:
                if not self._closed:
                    self._fail_all(TransportError("MCP server connection lost"))
                return
            except asyncio.CancelledError:
                return
            self._dispatch(msg)

    def _dispatch(self, msg: dict) -> None:
        if "id" in msg and ("result" in msg or "error" in msg):
            fut = self._pending.pop(msg["id"], None)
            if fut and not fut.done():
                if "error" in msg:
                    err = msg["error"]
                    fut.set_exception(MCPError(err.get("code", -1), err.get("message", ""), err.get("data")))
                else:
                    fut.set_result(msg.get("result", {}))
            return
        if "method" in msg and "id" in msg:
            asyncio.create_task(self._handle_server_request(msg))
            return
        if "method" in msg:
            if self.on_notification:
                self.on_notification(msg)

    async def _handle_server_request(self, msg: dict) -> None:
        method = msg.get("method")
        rid = msg["id"]
        if method == "ping":
            reply: dict = {"jsonrpc": "2.0", "id": rid, "result": {}}
        elif method == "roots/list":
            reply = {"jsonrpc": "2.0", "id": rid, "result": {"roots": []}}
        else:
            reply = {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32601, "message": f"client does not implement {method}"},
            }
        try:
            await self.transport.send(reply)
        except TransportError:
            pass

    async def _request(self, method: str, params: dict, *, cancel: Optional[CancelToken] = None) -> dict:
        rid = next(self._ids)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut

        unsub = None
        if cancel:
            def _cancel() -> None:
                if not fut.done():
                    asyncio.ensure_future(self._notify_cancelled(rid, "Cancelled by barge-in"))
                    fut.cancel()

            unsub = cancel.on_cancel(_cancel)

        try:
            await self.transport.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
            return await asyncio.wait_for(fut, timeout=self.request_timeout)
        except asyncio.CancelledError:
            raise CancelledError() from None
        except asyncio.TimeoutError as e:
            self._pending.pop(rid, None)
            raise MCPError(-32000, f"request timed out: {method}") from e
        finally:
            if unsub:
                unsub()

    async def _notify_cancelled(self, rid: int, reason: str) -> None:
        try:
            await self.transport.send(
                {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": rid, "reason": reason}}
            )
        except TransportError:
            pass

    def _fail_all(self, exc: Exception) -> None:
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(exc)
        self._pending.clear()

    async def list_tools(self) -> list[dict]:
        tools: list[dict] = []
        cursor: Optional[str] = None
        for _ in range(50):
            params = {"cursor": cursor} if cursor else {}
            result = await self._request("tools/list", params)
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools

    async def call_tool(
        self,
        name: str,
        arguments: dict,
        *,
        cancel: Optional[CancelToken] = None,
        timeout: Optional[float] = None,
    ) -> ToolResult:
        old_timeout = self.request_timeout
        if timeout is not None:
            self.request_timeout = timeout
        try:
            result = await self._request("tools/call", {"name": name, "arguments": arguments}, cancel=cancel)
        except MCPError as e:
            return ToolResult(call_id="", name=name, ok=False, content=e.message, error=e.message)
        finally:
            self.request_timeout = old_timeout

        return tool_result_from_mcp(name, result)

    async def close(self) -> None:
        self._closed = True
        if self._reader_task:
            self._reader_task.cancel()
        await self.transport.close()


def tool_result_from_mcp(name: str, result: dict) -> ToolResult:
    is_error = bool(result.get("isError"))
    parts: list[str] = []
    for item in result.get("content", []) or []:
        if item.get("type") == "text":
            parts.append(item.get("text", ""))
        elif item.get("type") == "resource":
            res = item.get("resource", {})
            parts.append(res.get("text") or res.get("uri", ""))
        else:
            parts.append(json.dumps(item)[:500])
    content = "\n".join(p for p in parts if p)
    structured = result.get("structuredContent")
    return ToolResult(
        call_id="",
        name=name,
        ok=not is_error,
        content=content,
        structured=structured if isinstance(structured, dict) else None,
        error=None if not is_error else (content or "tool error"),
    )


def tool_call_from_raw(raw: dict) -> ToolCall:
    fn = raw.get("function", raw)
    import uuid

    return ToolCall(
        id=raw.get("id") or f"call_{uuid.uuid4().hex[:8]}",
        name=fn.get("name", ""),
        arguments=fn.get("arguments") or {},
    )
