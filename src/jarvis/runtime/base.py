from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from jarvis.core.events import CancelToken
from jarvis.core.types import ToolResult, ToolSpec


@runtime_checkable
class ToolRuntime(Protocol):
    """Anything that can expose tools and execute them.

    `MCPClientManager` is the production implementation; `InMemoryToolRuntime`
    backs tests and the deterministic eval suite.
    """

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def tools(self) -> list[ToolSpec]: ...

    async def call(
        self,
        name: str,
        arguments: dict,
        *,
        cancel: Optional[CancelToken] = None,
    ) -> ToolResult: ...
