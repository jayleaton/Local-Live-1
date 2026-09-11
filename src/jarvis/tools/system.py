from __future__ import annotations

from collections import defaultdict
from typing import Callable, Optional

from jarvis.core.events import CancelToken
from jarvis.core.types import ToolResult, ToolSpec


class SystemRuntime:
    """Built-in introspection tools so the agent can report its own wiring.

    `system.mcp_status` answers "which local MCP servers/tools are connected?"
    without the user having to guess.
    """

    def __init__(self) -> None:
        self._tools_provider: Optional[Callable[[], list[ToolSpec]]] = None
        self._manager = None

    def bind(self, tools_provider: Callable[[], list[ToolSpec]], manager=None) -> None:
        self._tools_provider = tools_provider
        self._manager = manager

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="system.mcp_status",
                server="system",
                raw_name="mcp_status",
                description=(
                    "Report which local MCP servers and tools are connected to Jarvis right now "
                    "(e.g. the T3 Code workspace at t3.*)."
                ),
                input_schema={"type": "object", "properties": {}},
                read_only=True,
                idempotent=True,
            )
        ]

    async def call(self, name: str, arguments: dict, *, cancel: Optional[CancelToken] = None) -> ToolResult:
        if name != "system.mcp_status":
            return ToolResult(call_id="", name=name, ok=False, error=f"unknown tool: {name}")
        specs = self._tools_provider() if self._tools_provider else []
        by_server: dict[str, list[str]] = defaultdict(list)
        for spec in specs:
            by_server[spec.server].append(spec.raw_name or spec.name.split(".", 1)[-1])
        lines = ["Connected MCP/tool servers:"]
        if by_server:
            for server in sorted(by_server):
                lines.append(f"- {server}: {', '.join(sorted(set(by_server[server])))}")
        else:
            lines.append("- none")
        errors = getattr(self._manager, "errors", None) if self._manager is not None else None
        if errors:
            lines.append("Connection errors:")
            for server, err in sorted(errors.items()):
                lines.append(f"- {server}: {err}")
        return ToolResult(call_id="", name=name, ok=True, content="\n".join(lines))
