from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from jarvis.core.types import LLMResponse, Message, ToolCall, ToolSpec
from jarvis.harness.loop import AgentHarness
from jarvis.llm.scripted import ScriptedProvider
from jarvis.mcp.manager import MCPClientManager, ServerConfig
from jarvis.policy.gate import PolicyGate

ROOT = Path(__file__).resolve().parents[1]
SERVER = str(ROOT / "servers" / "demo_mcp_server.py")


def test_harness_drives_real_mcp_server():
    async def flow():
        manager = MCPClientManager([ServerConfig(name="demo", command=[sys.executable, SERVER])])

        def script(messages: list[Message], tools: list[ToolSpec]) -> LLMResponse:
            if any(m.role == "tool" for m in messages):
                last = next(m for m in reversed(messages) if m.role == "tool")
                return LLMResponse(text=f"final: {last.content}")
            return LLMResponse(tool_calls=[ToolCall(id="t1", name="demo.add", arguments={"a": 2, "b": 40})])

        harness = AgentHarness(ScriptedProvider(script), manager, PolicyGate(auto_approve=True))
        await harness.start()
        try:
            result = await harness.run("add 2 and 40")
        finally:
            await harness.stop()

        assert result.text.startswith("final:")
        assert "42" in result.text
        assert result.tool_records[0].result is not None
        assert result.tool_records[0].result.ok

    asyncio.run(flow())
