from __future__ import annotations

from jarvis.core.types import LLMResponse, Message, ToolCall
from jarvis.harness.loop import AgentHarness
from jarvis.llm.scripted import ScriptedProvider
from jarvis.policy.gate import PolicyGate
from jarvis.runtime.memory import InMemoryToolRuntime


def _harness() -> AgentHarness:
    return AgentHarness(
        ScriptedProvider(lambda m, t: LLMResponse(text="ok")),
        InMemoryToolRuntime(),
        PolicyGate(auto_approve=True),
    )


def test_remember_drops_assistant_tool_calls_even_with_text():
    h = _harness()
    messages = [
        Message.user("what time is it"),
        # assistant preamble + tool call: must be dropped, or the next request is invalid
        Message.assistant("Let me check.", [ToolCall(id="1", name="demo.now", arguments={})]),
        Message.tool("1", "demo.now", "12:00"),
        Message.assistant("It's 12:00."),
    ]
    h._remember(messages)
    assert all(not m.tool_calls for m in h.history), "history must not retain assistant tool_calls"
    assert [m.role for m in h.history] == ["user", "assistant"]
    assert h.history[-1].content == "It's 12:00."


def test_remember_keeps_pure_text_assistant():
    h = _harness()
    h._remember([Message.user("hi"), Message.assistant("hello there")])
    assert [m.role for m in h.history] == ["user", "assistant"]
