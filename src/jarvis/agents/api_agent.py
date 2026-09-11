from __future__ import annotations

from jarvis.agents.base import AgentResult, WorkerAgent
from jarvis.config import AgentConfig
from jarvis.core.types import Message
from jarvis.llm.openai_compat import OpenAICompatProvider


class APIAgent(WorkerAgent):
    """Worker agent backed by any OpenAI-compatible endpoint.

    The endpoint is given a large, self-contained task prompt and returns a
    result. This is deliberately *not* a conversational fallback: its output is
    handed back to the on-device model, which speaks it to the user.
    """

    def __init__(self, cfg: AgentConfig) -> None:
        self.cfg = cfg
        self.name = cfg.name
        self._provider = OpenAICompatProvider(
            cfg.base_url,
            cfg.model,
            api_key=cfg.resolved_api_key(),
            timeout=cfg.timeout,
            name=f"agent:{cfg.name}",
            extra_params=cfg.extra_params,
            reasoning_effort=cfg.reasoning_effort,
            strict_tools=cfg.strict_tools,
        )

    async def run(self, task: str, context: str = "") -> AgentResult:
        user = task if not context else f"Context:\n{context}\n\nTask:\n{task}"
        messages = [Message.system(self.cfg.system_prompt), Message.user(user)]
        try:
            resp = await self._provider.complete(
                messages,
                [],
                temperature=self.cfg.temperature,
                max_tokens=self.cfg.max_tokens,
            )
        except Exception as e:  # noqa: BLE001 - surfaced as an agent error
            return AgentResult(ok=False, content="", agent=self.name, error=f"{type(e).__name__}: {e}")
        return AgentResult(ok=True, content=resp.text.strip(), agent=self.name)
