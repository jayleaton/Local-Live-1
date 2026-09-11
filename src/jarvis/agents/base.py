from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentResult:
    ok: bool
    content: str
    agent: str
    error: Optional[str] = None


class WorkerAgent:
    """A higher-skilled agent the local model can dispatch a task to."""

    name: str = "worker"

    async def run(self, task: str, context: str = "") -> AgentResult:
        raise NotImplementedError
