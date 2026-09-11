from __future__ import annotations

import asyncio
import re

from jarvis.core.types import LLMResponse
from jarvis.eval.cases import _with
from jarvis.harness.loop import AgentHarness
from jarvis.llm.scripted import ScriptedProvider
from jarvis.policy.gate import PolicyGate
from jarvis.router.router import FastPathRule, Router
from jarvis.runtime.memory import InMemoryToolRuntime


def test_fast_path_emits_assistant_tool_calls_before_tool_result():
    runtime = InMemoryToolRuntime()
    for spec, fn in _with("now"):
        runtime.register(spec, fn)
    provider = ScriptedProvider(lambda m, t: LLMResponse(text="It's noon."))
    router = Router(
        fast_path_rules=[FastPathRule(tool_name="demo.now", patterns=[re.compile(r"what time")])],
    )
    harness = AgentHarness(provider, runtime, PolicyGate(auto_approve=True), router=router)

    async def flow():
        await harness.start()
        try:
            return await harness.run("what time is it?")
        finally:
            await harness.stop()

    result = asyncio.run(flow())
    messages = result.messages
    for i, m in enumerate(messages):
        if m.role == "tool":
            assert i > 0, "tool message must have a preceding assistant message"
            prev = messages[i - 1]
            assert prev.role == "assistant" and prev.tool_calls, (
                "every tool result must follow an assistant tool_calls message "
                f"(got {prev.role!r} before tool at {i})"
            )
