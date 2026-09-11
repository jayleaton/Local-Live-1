from __future__ import annotations

from jarvis.core.events import CancelToken
from jarvis.core.types import ToolResult, ToolSpec
from jarvis.runtime.base import ToolRuntime


class CompositeToolRuntime:
    """Fan-in over several tool runtimes (e.g. MCP servers + worker agents)."""

    def __init__(self, *runtimes: ToolRuntime) -> None:
        self._runtimes = list(runtimes)
        self._by_name: dict[str, ToolRuntime] = {}

    async def start(self) -> None:
        for rt in self._runtimes:
            await rt.start()
        self._by_name = {}
        for rt in self._runtimes:
            for spec in rt.tools():
                self._by_name[spec.name] = rt

    async def stop(self) -> None:
        for rt in self._runtimes:
            await rt.stop()

    def tools(self) -> list[ToolSpec]:
        out: list[ToolSpec] = []
        for rt in self._runtimes:
            out.extend(rt.tools())
        return out

    async def call(
        self,
        name: str,
        arguments: dict,
        *,
        cancel: CancelToken | None = None,
    ) -> ToolResult:
        rt = self._by_name.get(name)
        if rt is None:
            # runtime map may be stale if tools() changed; rebuild once.
            for candidate in self._runtimes:
                if any(s.name == name for s in candidate.tools()):
                    rt = candidate
                    break
        if rt is None:
            return ToolResult(call_id="", name=name, ok=False, error=f"unknown tool: {name}")
        return await rt.call(name, arguments, cancel=cancel)
