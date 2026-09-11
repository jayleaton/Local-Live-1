from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from jarvis.core.events import CancelToken
from jarvis.core.types import LLMResponse, Message, ToolCall, ToolSpec
from jarvis.harness.loop import RunResult
from jarvis.llm.base import LLMProvider
from jarvis.llm.scripted import ScriptedProvider
from jarvis.policy.gate import PolicyGate
from jarvis.router.router import FastPathRule
from jarvis.runtime.memory import InMemoryToolRuntime

ToolFn = Callable[[dict], str]
ScriptFn = Callable[[list[Message], list[ToolSpec]], LLMResponse]
CheckFn = Callable[[list[RunResult], InMemoryToolRuntime], "tuple[bool, str]"]
ProviderFactory = Callable[[CancelToken], LLMProvider]


def spec(
    name: str,
    *,
    server: str = "demo",
    read_only: bool = True,
    destructive: bool = False,
    description: str = "",
) -> ToolSpec:
    return ToolSpec(
        name=f"{server}.{name}",
        server=server,
        raw_name=name,
        description=description or name,
        read_only=read_only,
        destructive=destructive,
    )


def call(name: str, cid: str = "c1", **args) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=cid, name=name, arguments=args)])


def text(value: str) -> LLMResponse:
    return LLMResponse(text=value)


def has_tool_result(messages: list[Message]) -> bool:
    return any(m.role == "tool" for m in messages)


def last_tool(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.role == "tool":
            return m.content or ""
    return ""


@dataclass
class EvalCase:
    name: str
    turns: list[str]
    tools: list[tuple[ToolSpec, ToolFn]]
    script: Optional[ScriptFn] = None
    check: Optional[CheckFn] = None
    gate: Optional[PolicyGate] = None
    fast_paths: Optional[list[FastPathRule]] = None
    max_steps: int = 6
    cancel: str = "none"  # none | before | during
    provider_factory: Optional[ProviderFactory] = None


# ----------------------------------------------------------------------------
# Tools shared by cases
# ----------------------------------------------------------------------------


def _tools() -> dict[str, tuple[ToolSpec, ToolFn]]:
    def explode(_args: dict) -> str:
        raise RuntimeError("boom")

    return {
        "add": (spec("add"), lambda a: str(int(a["a"]) + int(a["b"]))),
        "now": (spec("now"), lambda a: "12:00:00"),
        "save_note": (spec("save_note", read_only=False), lambda a: "saved note 1"),
        "delete_note": (spec("delete_note", read_only=False, destructive=True), lambda a: "deleted note 1"),
        "flaky": (spec("flaky"), explode),
    }


def _with(*names: str) -> list[tuple[ToolSpec, ToolFn]]:
    tools = _tools()
    return [tools[n] for n in names]


# ----------------------------------------------------------------------------
# Case definitions
# ----------------------------------------------------------------------------

DIRECT = EvalCase(
    name="direct_answer",
    turns=["hello there"],
    tools=[],
    script=lambda m, t: text("Hi! How can I help?"),
    check=lambda rs, rt: (rs[-1].text == "Hi! How can I help?", rs[-1].text),
)

SINGLE_TOOL = EvalCase(
    name="single_read_tool",
    turns=["add 2 and 3"],
    tools=_with("add"),
    script=lambda m, t: text("The sum is 5.") if has_tool_result(m) else call("demo.add", a=2, b=3),
    check=lambda rs, rt: (
        any(c[0] == "demo.add" for c in rt.calls) and "5" in rs[-1].text,
        f"calls={rt.calls} text={rs[-1].text!r}",
    ),
)

ERROR_RECOVERY = EvalCase(
    name="tool_error_then_recover",
    turns=["use the flaky tool"],
    tools=_with("flaky"),
    script=lambda m, t: text("That tool failed, sorry.") if "ERROR" in last_tool(m) else call("demo.flaky"),
    check=lambda rs, rt: (
        rs[-1].tool_records[-1].result is not None
        and not rs[-1].tool_records[-1].result.ok
        and "sorry" in rs[-1].text,
        f"records={[(r.call.name, r.result.ok if r.result else None) for r in rs[-1].tool_records]}",
    ),
)

DESTRUCTIVE_DENIED = EvalCase(
    name="destructive_denied_without_confirmer",
    turns=["delete note 1"],
    tools=_with("delete_note"),
    gate=PolicyGate(auto_approve=False, confirmer=None),
    script=lambda m, t: text("Done.") if has_tool_result(m) else call("demo.delete_note", id="1"),
    check=lambda rs, rt: (
        "demo.delete_note" in rs[-1].denied and not rt.calls,
        f"denied={rs[-1].denied} executed={rt.calls}",
    ),
)

DESTRUCTIVE_CONFIRMED = EvalCase(
    name="destructive_confirmed",
    turns=["delete note 1"],
    tools=_with("delete_note"),
    gate=PolicyGate(auto_approve=False, confirmer=lambda c, s: True),
    script=lambda m, t: text("Deleted it.") if has_tool_result(m) else call("demo.delete_note", id="1"),
    check=lambda rs, rt: (
        any(c[0] == "demo.delete_note" for c in rt.calls) and "Deleted" in rs[-1].text,
        f"executed={rt.calls}",
    ),
)

READ_ONLY_MODE = EvalCase(
    name="read_only_mode_blocks_write",
    turns=["save a note"],
    tools=_with("save_note"),
    gate=PolicyGate(auto_approve=True, read_only_only=True),
    script=lambda m, t: text("ok") if has_tool_result(m) else call("demo.save_note", text="hi"),
    check=lambda rs, rt: ("demo.save_note" in rs[-1].denied and not rt.calls, f"denied={rs[-1].denied}"),
)

DENY_PATTERN = EvalCase(
    name="deny_pattern_blocks",
    turns=["save a note"],
    tools=_with("save_note"),
    gate=PolicyGate(auto_approve=True, deny_patterns=["demo.save*"]),
    script=lambda m, t: text("ok") if has_tool_result(m) else call("demo.save_note", text="hi"),
    check=lambda rs, rt: ("demo.save_note" in rs[-1].denied and not rt.calls, f"denied={rs[-1].denied}"),
)

FAST_PATH = EvalCase(
    name="fast_path_time",
    turns=["what time is it?"],
    tools=_with("now"),
    fast_paths=[FastPathRule(tool_name="demo.now", patterns=[re.compile(r"what time")])],
    script=lambda m, t: text("It's 12:00:00.") if has_tool_result(m) else text("fallback"),
    check=lambda rs, rt: (
        any(c[0] == "demo.now" for c in rt.calls) and "12:00" in rs[-1].text,
        f"calls={rt.calls} text={rs[-1].text!r}",
    ),
)

STEP_BUDGET = EvalCase(
    name="step_budget_exceeded",
    turns=["loop forever"],
    tools=_with("add"),
    max_steps=2,
    script=lambda m, t: call("demo.add", a=1, b=1),
    check=lambda rs, rt: (rs[-1].steps == 2 and "step budget" in rs[-1].text, f"steps={rs[-1].steps}"),
)

UNKNOWN_TOOL = EvalCase(
    name="unknown_tool_denied",
    turns=["call a ghost"],
    tools=_with("add"),
    script=lambda m, t: text("ok") if has_tool_result(m) else call("demo.nope"),
    check=lambda rs, rt: ("demo.nope" in rs[-1].denied and not rt.calls, f"denied={rs[-1].denied}"),
)

CANCEL_BEFORE = EvalCase(
    name="cancel_before_run",
    turns=["are you there?"],
    tools=_with("add"),
    cancel="before",
    script=lambda m, t: text("should not be reached"),
    check=lambda rs, rt: (rs[-1].cancelled and rs[-1].text == "", f"cancelled={rs[-1].cancelled}"),
)


def _cancel_during_provider(token: CancelToken) -> LLMProvider:
    def script(m: list[Message], t: list[ToolSpec]) -> LLMResponse:
        token.cancel()
        return call("demo.add", a=1, b=1)

    return ScriptedProvider(script)


CANCEL_DURING = EvalCase(
    name="cancel_during_tool",
    turns=["add one and one"],
    tools=_with("add"),
    cancel="during",
    provider_factory=_cancel_during_provider,
    check=lambda rs, rt: (rs[-1].cancelled, f"cancelled={rs[-1].cancelled}"),
)

MULTI_TURN = EvalCase(
    name="history_retained_across_turns",
    turns=["what time is it?", "and again"],
    tools=_with("now"),
    script=lambda m, t: text("Twelve o'clock."),
    check=lambda rs, rt: (
        len(rs) == 2 and rs[-1].text == "Twelve o'clock.",
        f"turns={len(rs)}",
    ),
)


def all_cases() -> list[EvalCase]:
    return [
        DIRECT,
        SINGLE_TOOL,
        ERROR_RECOVERY,
        DESTRUCTIVE_DENIED,
        DESTRUCTIVE_CONFIRMED,
        READ_ONLY_MODE,
        DENY_PATTERN,
        FAST_PATH,
        STEP_BUDGET,
        UNKNOWN_TOOL,
        CANCEL_BEFORE,
        CANCEL_DURING,
        MULTI_TURN,
    ]
