from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Optional, Protocol

from jarvis.core.types import Message, ToolCall, ToolSpec

# Turns that require high skill and should be handed to a worker agent.
DEFAULT_DISPATCH_PATTERNS = [
    r"\b(code|coding|program|programming|script|function|class|module|library|sdk|api|endpoint|database|sql|schema|algorithm|regex)\b",
    r"\b(bug|debug|stack ?trace|error|exception|crash|fix|refactor|implement|compile|build|deploy|migrate)\b",
    r"\b(repo|repository|git|commit|branch|pull request|merge|ci|test suite|unit test|integration test)\b",
    r"\b(write|create|generate|update|modify|change|add|remove|delete)\b.{0,40}\b(file|code|function|script|class|component|app|website|page|test|config)\b",
    r"\b(research|look ?up|search (the )?(web|docs|documentation)|summari[sz]e this|analy[sz]e this document)\b",
    r"\b(automate|orchestrate|plan (out )?a project|multi[- ]?step)\b",
]

# Turns that must stay local: smalltalk, relationship, on-device actions.
DEFAULT_LOCAL_PATTERNS = [
    r"^(hi|hey|hello|yo|good (morning|afternoon|evening))\b",
    r"\b(how are you|who are you|what are you|thanks|thank you|cheers|nice one|good job)\b",
    r"\b(stop|cancel|never ?mind|nevermind|quiet|be quiet|shut ?up)\b",
    r"\b(what('?s| is) the time|what time is it|set a timer|remind me)\b",
]


@dataclass
class DispatchDecision:
    mode: str  # "local" | "dispatch"
    tasks: list[ToolCall] = field(default_factory=list)
    reason: str = ""


class Dispatcher(Protocol):
    def decide(self, text: str, tools: list[ToolSpec], history: list[Message]) -> DispatchDecision: ...


class HeuristicDispatcher:
    """Cheap, deterministic planner that decides local answer vs agent dispatch.

    Kept deliberately separate from the local conversational model: the model
    only talks, this decides when to compose and send a larger task prompt to a
    worker agent (an MCP-exposed agent or a built-in API agent).
    """

    def __init__(
        self,
        *,
        dispatch_patterns: Optional[list[str]] = None,
        local_patterns: Optional[list[str]] = None,
        max_tasks: int = 1,
    ) -> None:
        self.dispatch_patterns = [re.compile(p, re.IGNORECASE) for p in (dispatch_patterns or DEFAULT_DISPATCH_PATTERNS)]
        self.local_patterns = [re.compile(p, re.IGNORECASE) for p in (local_patterns or DEFAULT_LOCAL_PATTERNS)]
        self.max_tasks = max(1, max_tasks)

    def decide(self, text: str, tools: list[ToolSpec], history: list[Message]) -> DispatchDecision:
        agent_tools = [t for t in tools if t.server == "agent"]
        if not agent_tools:
            return DispatchDecision("local", reason="no worker agents configured")

        if any(p.search(text) for p in self.local_patterns):
            return DispatchDecision("local", reason="smalltalk/on-device intent")

        if not any(p.search(text) for p in self.dispatch_patterns):
            return DispatchDecision("local", reason="no dispatch intent")

        tool = self._pick_agent(text, agent_tools)
        task = self._compose_task(text, history)
        context = self._recent_context(history)
        call = ToolCall(
            id=f"dispatch_{uuid.uuid4().hex[:8]}",
            name=tool.name,
            arguments={"task": task, "context": context} if context else {"task": task},
        )
        return DispatchDecision("dispatch", tasks=[call], reason=f"matched agent tool {tool.name}")

    @staticmethod
    def _pick_agent(text: str, agent_tools: list[ToolSpec]) -> ToolSpec:
        lowered = text.lower()
        best = None
        best_score = 0
        for tool in agent_tools:
            haystack = f"{tool.name} {tool.description}".lower()
            score = sum(1 for word in set(lowered.split()) if len(word) > 3 and word in haystack)
            if score > best_score:
                best, best_score = tool, score
        return best or agent_tools[0]

    @staticmethod
    def _recent_context(history: list[Message], turns: int = 4) -> str:
        lines: list[str] = []
        for m in history[-turns * 2 :]:
            if m.role in ("user", "assistant") and m.content:
                lines.append(f"{m.role}: {m.content}")
        return "\n".join(lines)

    @staticmethod
    def _compose_task(text: str, history: list[Message]) -> str:
        context = HeuristicDispatcher._recent_context(history)
        if context:
            return f"User request (via voice): {text}\n\nRecent conversation:\n{context}"
        return f"User request (via voice): {text}"
