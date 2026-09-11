from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Optional


class TransportError(RuntimeError):
    pass


class Transport(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def send(self, message: dict[str, Any]) -> None: ...

    @abstractmethod
    async def receive(self) -> dict[str, Any]: ...

    @abstractmethod
    async def close(self) -> None: ...


class StdioTransport(Transport):
    """Newline-delimited JSON-RPC over a child process's stdio.

    The default transport for local MCP servers per the MCP spec.
    """

    def __init__(
        self,
        command: list[str],
        *,
        env: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None,
        stderr_to: Optional[list[str]] = None,
    ) -> None:
        self.command = command
        self.env = {**os.environ, **(env or {})}
        self.cwd = cwd
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._stderr_lines: list[str] = stderr_to if stderr_to is not None else []
        self._stderr_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
                cwd=self.cwd,
            )
        except FileNotFoundError as e:
            raise TransportError(f"command not found: {self.command[0]}") from e
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _drain_stderr(self) -> None:
        assert self._proc and self._proc.stderr
        while True:
            line = await self._proc.stderr.readline()
            if not line:
                return
            self._stderr_lines.append(line.decode("utf-8", "replace").rstrip())

    async def send(self, message: dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise TransportError("transport not started")
        data = (json.dumps(message) + "\n").encode("utf-8")
        self._proc.stdin.write(data)
        await self._proc.stdin.drain()

    async def receive(self) -> dict[str, Any]:
        if not self._proc or not self._proc.stdout:
            raise TransportError("transport not started")
        line = await self._proc.stdout.readline()
        if not line:
            raise TransportError("server closed stdout (process exited?)")
        try:
            return json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise TransportError(f"invalid JSON from server: {line[:200]!r}") from e

    async def close(self) -> None:
        if self._stderr_task:
            self._stderr_task.cancel()
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    self._proc.kill()
                except ProcessLookupError:
                    pass


def _parse_http_messages(content_type: str, body: bytes) -> list[dict[str, Any]]:
    """Extract JSON-RPC messages from a streamable-HTTP response (JSON or SSE)."""
    if not body:
        return []
    text = body.decode("utf-8", "replace")
    if "text/event-stream" in (content_type or ""):
        messages: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                messages.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
        return messages
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else [parsed]


class StreamableHttpTransport(Transport):
    """MCP Streamable HTTP transport.

    POSTs each JSON-RPC message to a single endpoint and enqueues the JSON-RPC
    responses (JSON or SSE). Supports optional session ids and auth headers, so
    it connects to remote servers (e.g. z.ai web search) and loopback HTTP
    servers (e.g. the T3 workspace MCP).
    """

    def __init__(
        self,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        timeout: float = 60.0,
    ) -> None:
        self.url = url
        self.headers = dict(headers or {})
        self.timeout = timeout
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._session_id: Optional[str] = None
        self._protocol_version: Optional[str] = None

    async def start(self) -> None:
        return None

    def _post(self, data: bytes, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            return e.code, {k.lower(): v for k, v in e.headers.items()}, body
        except Exception as e:  # noqa: BLE001
            raise TransportError(f"HTTP transport error: {type(e).__name__}: {e}") from e

    async def send(self, message: dict[str, Any]) -> None:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.headers,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        if self._protocol_version:
            headers["MCP-Protocol-Version"] = self._protocol_version
        status, resp_headers, body = await asyncio.to_thread(
            self._post, json.dumps(message).encode("utf-8"), headers
        )
        if resp_headers.get("mcp-session-id"):
            self._session_id = resp_headers["mcp-session-id"]
        messages = _parse_http_messages(resp_headers.get("content-type", ""), body)
        for msg in messages:
            if isinstance(msg, dict):
                if msg.get("result", {}).get("protocolVersion"):
                    self._protocol_version = msg["result"]["protocolVersion"]
                await self._queue.put(msg)
        if not messages and status >= 400:
            raise TransportError(f"HTTP {status}: {body.decode('utf-8', 'replace')[:200]}")

    async def receive(self) -> dict[str, Any]:
        return await self._queue.get()

    async def close(self) -> None:
        return None
