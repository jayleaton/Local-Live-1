from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from jarvis.core.events import CancelToken
from jarvis.eval.cases import EvalCase, all_cases
from jarvis.harness.loop import AgentHarness, HarnessConfig, RunResult
from jarvis.llm.scripted import ScriptedProvider
from jarvis.policy.gate import PolicyGate
from jarvis.router.router import Router
from jarvis.runtime.memory import InMemoryToolRuntime


@dataclass
class EvalOutcome:
    name: str
    passed: bool
    detail: str
    duration_ms: float


async def run_case(case: EvalCase) -> EvalOutcome:
    runtime = InMemoryToolRuntime()
    for tool_spec, fn in case.tools:
        runtime.register(tool_spec, fn)

    token = CancelToken()
    if case.provider_factory:
        provider = case.provider_factory(token)
    else:
        assert case.script is not None
        provider = ScriptedProvider(case.script)

    gate = case.gate or PolicyGate(auto_approve=True)
    router = None
    if case.fast_paths:
        router = Router(fast_path_rules=case.fast_paths)

    harness = AgentHarness(
        provider,
        runtime,
        gate,
        router=router,
        config=HarnessConfig(max_steps=case.max_steps),
    )

    results: list[RunResult] = []
    start = time.perf_counter()
    await harness.start()
    try:
        if case.cancel == "before":
            token.cancel()
        for turn in case.turns:
            results.append(await harness.run(turn, cancel=token))
    finally:
        await harness.stop()

    duration = (time.perf_counter() - start) * 1000
    if case.check is None:
        passed, detail = True, "no assertions"
    else:
        try:
            passed, detail = case.check(results, runtime)
        except Exception as e:  # noqa: BLE001
            passed, detail = False, f"check raised {type(e).__name__}: {e}"
    return EvalOutcome(name=case.name, passed=passed, detail=detail, duration_ms=duration)


async def run_suite(cases: list[EvalCase] | None = None) -> list[EvalOutcome]:
    outcomes = []
    for case in cases or all_cases():
        outcomes.append(await run_case(case))
    return outcomes


def run_suite_sync(cases: list[EvalCase] | None = None) -> list[EvalOutcome]:
    return asyncio.run(run_suite(cases))
