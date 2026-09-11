from __future__ import annotations

import time
from typing import Awaitable, Callable, Optional

from jarvis.core.events import CancelToken
from jarvis.core.types import ToolResult, ToolSpec

ToolFn = Callable[[dict], Awaitable[str] | str]


class InMemoryToolRuntime:
    """Dict-backed tool runtime for tests and evals."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._fns: dict[str, ToolFn] = {}
        self.calls: list[tuple[str, dict]] = []

    def register(
        self,
        spec: ToolSpec,
        fn: ToolFn,
    ) -> None:
        self._specs[spec.name] = spec
        self._fns[spec.name] = fn

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def tools(self) -> list[ToolSpec]:
        return list(self._specs.values())

    async def call(
        self,
        name: str,
        arguments: dict,
        *,
        cancel: Optional[CancelToken] = None,
    ) -> ToolResult:
        if cancel:
            cancel.raise_if_cancelled()
        if name not in self._fns:
            return ToolResult(call_id="", name=name, ok=False, error=f"unknown tool: {name}")
        self.calls.append((name, dict(arguments)))
        start = time.perf_counter()
        try:
            out = self._fns[name](arguments)
            if isinstance(out, Awaitable):
                out = await out
            return ToolResult(
                call_id="",
                name=name,
                ok=True,
                content=str(out),
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as e:  # noqa: BLE001 - surfaced to the model as isError
            return ToolResult(
                call_id="",
                name=name,
                ok=False,
                content=str(e),
                error=f"{type(e).__name__}: {e}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
