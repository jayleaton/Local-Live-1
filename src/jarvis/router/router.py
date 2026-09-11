from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

from jarvis.core.types import ToolCall

ArgBuilder = Callable[[re.Match, str], dict]


@dataclass
class FastPathRule:
    """Deterministic intent that bypasses the model entirely.

    Fast-paths are the cheapest latency and highest-reliability path. Use them
    for high-frequency, unambiguous intents (time, timers, device toggles).
    """

    tool_name: str
    patterns: list[re.Pattern]
    build_args: ArgBuilder = lambda m, t: {}
    response_template: str = ""
    name: str = ""


@dataclass
class Plan:
    kind: Literal["tool", "answer"]
    tool_calls: list[ToolCall] = field(default_factory=list)
    text: str = ""


class Router:
    """Deterministic fast-path router.

    The local model owns all conversation; worker agents are invoked by the
    separate dispatcher, never by swapping the reply provider. This router only
    short-circuits unambiguous intents straight to a tool.
    """

    def __init__(self, *, fast_path_rules: Optional[list[FastPathRule]] = None) -> None:
        self.fast_path_rules = list(fast_path_rules or [])

    def plan_fast_path(self, text: str, available_tools: set[str]) -> Optional[Plan]:
        lowered = text.lower().strip()
        for rule in self.fast_path_rules:
            if available_tools and rule.tool_name not in available_tools:
                continue
            for pattern in rule.patterns:
                m = pattern.search(lowered)
                if m:
                    if rule.response_template and not rule.tool_name:
                        return Plan(kind="answer", text=rule.response_template.format(query=text))
                    call = ToolCall(
                        id=f"fp_{uuid.uuid4().hex[:8]}",
                        name=rule.tool_name,
                        arguments=rule.build_args(m, text),
                    )
                    return Plan(kind="tool", tool_calls=[call], text=rule.response_template)
        return None


def build_default_fast_paths(available_tools: set[str]) -> list[FastPathRule]:
    rules: list[FastPathRule] = []
    time_tool = _match_any(available_tools, ["now", "time", "clock", "get_time"])
    if time_tool:
        rules.append(
            FastPathRule(
                tool_name=time_tool,
                patterns=[re.compile(r"\b(what('?s| is) the time|what time is it|current time)\b")],
                build_args=lambda m, t: {},
                name="time",
            )
        )
    return rules


def _match_any(tools: set[str], suffixes: list[str]) -> Optional[str]:
    for tool in sorted(tools):
        for suffix in suffixes:
            if tool.endswith("." + suffix) or tool.endswith("__" + suffix) or tool == suffix:
                return tool
    return None
