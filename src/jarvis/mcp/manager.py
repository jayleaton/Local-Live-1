from __future__ import annotations

import fnmatch
import time
from dataclasses import dataclass, field
from typing import Optional

from jarvis.core.events import CancelToken, CancelledError
from jarvis.core.types import ToolResult, ToolSpec
from jarvis.mcp.client import DEFAULT_PROTOCOL_VERSION, MCPClient
from jarvis.mcp.transport import StdioTransport, StreamableHttpTransport, Transport


@dataclass
class ServerConfig:
    name: str
    command: list[str] = field(default_factory=list)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None
    enabled: bool = True
    # Progressive disclosure: only advertise tools matching these globs (empty = all).
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)
    request_timeout: float = 30.0


class MCPClientManager:
    """Aggregates many MCP servers into one namespaced, cached tool surface.

    Implements the `ToolRuntime` protocol. One persistent client per server;
    tools are namespaced `<server>.<tool>` and discovered once at start.
    """

    def __init__(
        self,
        servers: list[ServerConfig] | None = None,
        *,
        protocol_version: str | None = None,
    ) -> None:
        self.server_configs = list(servers or [])
        self.protocol_version = protocol_version
        self.errors: dict[str, str] = {}
        self._clients: dict[str, MCPClient] = {}
        self._transport_factories: dict[str, callable] = {}
        self._specs: dict[str, ToolSpec] = {}
        self._index: dict[str, tuple[str, str]] = {}  # namespaced -> (server, raw)
        self._started = False

    def add_server(
        self,
        config: ServerConfig,
        *,
        transport_factory: Optional[callable] = None,
    ) -> None:
        self.server_configs.append(config)
        if transport_factory:
            self._transport_factories[config.name] = transport_factory

    def _make_transport(self, cfg: ServerConfig) -> Transport:
        factory = self._transport_factories.get(cfg.name)
        if factory:
            return factory(cfg)
        if cfg.url:
            return StreamableHttpTransport(cfg.url, headers=cfg.headers, timeout=cfg.request_timeout)
        return StdioTransport(cfg.command, env=cfg.env, cwd=cfg.cwd)

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        for cfg in self.server_configs:
            if not cfg.enabled:
                continue
            try:
                await self._start_server(cfg)
            except Exception as e:  # noqa: BLE001 - one bad server must not kill the rest
                self.errors[cfg.name] = f"{type(e).__name__}: {e}"

    async def _start_server(self, cfg: ServerConfig) -> None:
        client = MCPClient(
            cfg.name,
            self._make_transport(cfg),
            protocol_version=self.protocol_version or DEFAULT_PROTOCOL_VERSION,
            request_timeout=cfg.request_timeout,
        )
        await client.start()
        raw_tools = await client.list_tools()
        self._clients[cfg.name] = client
        for raw in raw_tools:
            raw_name = raw.get("name", "")
            if not raw_name or not self._tool_visible(cfg, raw_name):
                continue
            spec = build_spec(cfg.name, raw_name, raw)
            self._specs[spec.name] = spec
            self._index[spec.name] = (cfg.name, raw_name)

    @staticmethod
    def _tool_visible(cfg: ServerConfig, raw_name: str) -> bool:
        if cfg.allow and not any(fnmatch.fnmatch(raw_name, p) for p in cfg.allow):
            return False
        if cfg.deny and any(fnmatch.fnmatch(raw_name, p) for p in cfg.deny):
            return False
        return True

    def tools(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def tool(self, name: str) -> Optional[ToolSpec]:
        return self._specs.get(name)

    async def call(
        self,
        name: str,
        arguments: dict,
        *,
        cancel: Optional[CancelToken] = None,
        timeout: Optional[float] = None,
    ) -> ToolResult:
        target = self._index.get(name)
        if not target:
            return ToolResult(call_id="", name=name, ok=False, error=f"unknown tool: {name}")
        server_name, raw_name = target
        client = self._clients.get(server_name)
        if not client:
            return ToolResult(call_id="", name=name, ok=False, error=f"server not connected: {server_name}")
        start = time.perf_counter()
        try:
            result = await client.call_tool(raw_name, arguments, cancel=cancel, timeout=timeout)
        except CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            return ToolResult(call_id="", name=name, ok=False, error=f"{type(e).__name__}: {e}")
        result.name = name
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    async def stop(self) -> None:
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:
                pass
        self._clients.clear()


def build_spec(server: str, raw_name: str, raw: dict) -> ToolSpec:
    ann = raw.get("annotations") or {}
    return ToolSpec(
        name=f"{server}.{raw_name}",
        server=server,
        raw_name=raw_name,
        description=raw.get("description", "") or "",
        input_schema=raw.get("inputSchema") or raw.get("input_schema") or {"type": "object", "properties": {}},
        output_schema=raw.get("outputSchema"),
        read_only=bool(ann.get("readOnlyHint", False)),
        destructive=bool(ann.get("destructiveHint", False)),
        idempotent=bool(ann.get("idempotentHint", False)),
    )
