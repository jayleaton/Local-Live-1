from __future__ import annotations

import asyncio

from jarvis.agents.base import AgentResult, WorkerAgent
from jarvis.agents.runtime import AgentRuntime, agent_tool_name
from jarvis.core.types import LLMResponse, Message, ToolSpec
from jarvis.dispatch.dispatcher import HeuristicDispatcher
from jarvis.harness.loop import AgentHarness, HarnessConfig
from jarvis.llm.scripted import ScriptedProvider
from jarvis.policy.gate import PolicyGate
from jarvis.runtime.composite import CompositeToolRuntime
from jarvis.runtime.memory import InMemoryToolRuntime


class RecordingAgent(WorkerAgent):
    def __init__(self, name="worker"):
        self.name = name
        self.calls: list[tuple[str, str]] = []

    async def run(self, task: str, context: str = "") -> AgentResult:
        self.calls.append((task, context))
        return AgentResult(ok=True, content="SORTED_RESULT", agent=self.name)


def _agent_tool(name="agent.worker"):
    from jarvis.core.types import ToolSpec

    return ToolSpec(name=name, server="agent", raw_name="worker", description="worker agent", read_only=False)


def test_dispatcher_local_when_no_agents():
    d = HeuristicDispatcher()
    decision = d.decide("write a python function", [], [])
    assert decision.mode == "local"


def test_dispatcher_smalltalk_stays_local():
    d = HeuristicDispatcher()
    decision = d.decide("hey, how are you?", [_agent_tool()], [])
    assert decision.mode == "local"


def test_dispatcher_escalates_coding_task():
    d = HeuristicDispatcher()
    decision = d.decide("write a python function to sort a list and add tests", [_agent_tool()], [])
    assert decision.mode == "dispatch"
    assert decision.tasks[0].name == "agent.worker"
    assert "sort a list" in decision.tasks[0].arguments["task"]


def test_agent_runtime_call():
    agent = RecordingAgent()
    runtime = AgentRuntime()
    runtime.register(agent)

    result = asyncio.run(runtime.call(agent_tool_name("worker"), {"task": "do a thing", "context": "ctx"}))
    assert result.ok and result.content == "SORTED_RESULT"
    assert agent.calls == [("do a thing", "ctx")]


def test_composite_routes_by_name():
    agent = RecordingAgent()
    agent_runtime = AgentRuntime()
    agent_runtime.register(agent)
    mcp = InMemoryToolRuntime()
    from jarvis.eval.cases import _with

    for spec, fn in _with("add"):
        mcp.register(spec, fn)
    comp = CompositeToolRuntime(mcp, agent_runtime)
    asyncio.run(comp.start())
    names = {t.name for t in comp.tools()}
    assert {"demo.add", "agent.worker"} <= names
    assert asyncio.run(comp.call("agent.worker", {"task": "x"})).ok
    assert asyncio.run(comp.call("demo.add", {"a": 1, "b": 2})).ok


def test_harness_dispatches_then_local_model_relays():
    agent = RecordingAgent()
    agent_runtime = AgentRuntime()
    agent_runtime.register(agent)

    # Local model never sees tools; it only relays the agent's result.
    def script(messages: list[Message], tools: list[ToolSpec]) -> LLMResponse:
        assert tools == [], "local model must be called without tools"
        return LLMResponse(text="I sorted it for you.")

    provider = ScriptedProvider(script, supports_tools=False)
    gate = PolicyGate(allowed_servers=["agent"], auto_approve=True)
    dispatcher = HeuristicDispatcher()
    harness = AgentHarness(
        provider,
        agent_runtime,
        gate,
        dispatcher=dispatcher,
        config=HarnessConfig(max_steps=4),
    )

    async def flow():
        await harness.start()
        try:
            return await harness.run("write a python function to sort a list")
        finally:
            await harness.stop()

    result = asyncio.run(flow())
    assert result.text == "I sorted it for you."
    assert len(agent.calls) == 1
    assert "sort a list" in agent.calls[0][0]
    assert any(r.call.name == "agent.worker" for r in result.tool_records)
