from __future__ import annotations

import time
from typing import Optional

from jarvis.agents.api_agent import APIAgent
from jarvis.agents.base import AgentResult, WorkerAgent
from jarvis.config import AgentConfig
from jarvis.core.events import CancelToken
from jarvis.core.types import ToolResult, ToolSpec

AGENT_SERVER = "agent"
AGENT_TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "task": {"type": "string", "description": "A complete, self-contained task prompt for the agent."},
        "context": {"type": "string", "description": "Optional relevant context (files, prior results, constraints)."},
    },
    "required": ["task"],
}


def agent_tool_name(name: str) -> str:
    return f"{AGENT_SERVER}.{name}"


class AgentRuntime:
    """Exposes each configured worker agent as a callable tool.

    Implements the `ToolRuntime` protocol so agents flow through the same policy
    gate, audit log, and cancellation path as MCP tools.
    """

    def __init__(self, agents: list[AgentConfig] | None = None) -> None:
        self._agents: dict[str, WorkerAgent] = {}
        for cfg in agents or []:
            self.register(APIAgent(cfg))

    def register(self, agent: WorkerAgent) -> None:
        self._agents[agent.name] = agent

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def tools(self) -> list[ToolSpec]:
        out: list[ToolSpec] = []
        for name, agent in self._agents.items():
            cfg = getattr(agent, "cfg", None)
            desc = (getattr(cfg, "description", "") or "").strip() or (
                f"Dispatch a task to the '{name}' worker agent."
            )
            out.append(
                ToolSpec(
                    name=agent_tool_name(name),
                    server=AGENT_SERVER,
                    raw_name=name,
                    description=desc,
                    input_schema=AGENT_TASK_SCHEMA,
                    read_only=False,
                    destructive=False,
                    idempotent=False,
                )
            )
        return out

    async def call(
        self,
        name: str,
        arguments: dict,
        *,
        cancel: Optional[CancelToken] = None,
    ) -> ToolResult:
        if cancel:
            cancel.raise_if_cancelled()
        if not name.startswith(f"{AGENT_SERVER}."):
            return ToolResult(call_id="", name=name, ok=False, error=f"unknown agent tool: {name}")
        agent_name = name.split(".", 1)[1]
        agent = self._agents.get(agent_name)
        if agent is None:
            return ToolResult(call_id="", name=name, ok=False, error=f"unknown agent: {agent_name}")
        task = str(arguments.get("task", "")).strip()
        context = str(arguments.get("context", "")).strip()
        if not task:
            return ToolResult(call_id="", name=name, ok=False, error="missing required field: task")
        start = time.perf_counter()
        result: AgentResult = await agent.run(task, context)
        return ToolResult(
            call_id="",
            name=name,
            ok=result.ok,
            content=result.content,
            error=result.error,
            duration_ms=(time.perf_counter() - start) * 1000,
        )
