from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

from jarvis.config import JarvisConfig, ModelConfig
from jarvis.core.events import CancelToken
from jarvis.core.types import ToolSpec
from jarvis.eval.runner import run_suite
from jarvis.harness.loop import AgentHarness, HarnessConfig
from jarvis.llm.openai_compat import OpenAICompatProvider
from jarvis.llm.scripted import ScriptedProvider
from jarvis.mcp.manager import MCPClientManager
from jarvis.policy.gate import PolicyGate
from jarvis.router.router import Router, build_default_fast_paths
from jarvis.runtime.memory import InMemoryToolRuntime


def _find_config(explicit: Optional[str]) -> Optional[Path]:
    if explicit:
        return Path(explicit)
    env_config = os.environ.get("JARVIS_CONFIG")
    if env_config and Path(env_config).exists():
        return Path(env_config)
    for candidate in ("jarvis.config.json", "jarvis.config.example.json"):
        if Path(candidate).exists():
            return Path(candidate)
    return None


def _provider_from(cfg: ModelConfig) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        cfg.base_url,
        cfg.model,
        api_key=cfg.resolved_api_key(),
        timeout=cfg.timeout,
        name=f"openai-compat:{cfg.model}",
        extra_params=cfg.extra_params,
        reasoning_effort=cfg.reasoning_effort,
        strict_tools=cfg.strict_tools,
    )


async def _build_harness(cfg: JarvisConfig, confirmer, *, auto_approve: Optional[bool] = None) -> AgentHarness:
    from jarvis.agents.runtime import AgentRuntime
    from jarvis.dispatch.dispatcher import HeuristicDispatcher
    from jarvis.llm.mlx_local import MLXProvider
    from jarvis.runtime.composite import CompositeToolRuntime
    from jarvis.tools.system import SystemRuntime
    from jarvis.tools.web import WebRuntime

    manager = MCPClientManager(list(cfg.servers.values()))
    await manager.start()
    tools = manager.tools()

    # The on-device model is the default voice brain; the API model is an option
    # (settings toggle) or the fallback when no local model is configured.
    if cfg.response_mode != "api" and cfg.local is not None:
        provider = MLXProvider(
            cfg.local.model,
            temperature=cfg.local.temperature,
            max_tokens=cfg.local.max_tokens,
        )
    else:
        provider = _provider_from(cfg.model)

    agent_runtime = AgentRuntime(list(cfg.agents.values()))
    web_runtime = WebRuntime()
    system_runtime = SystemRuntime()
    runtime = CompositeToolRuntime(manager, agent_runtime, web_runtime, system_runtime)
    system_runtime.bind(lambda: runtime.tools(), manager)

    dispatcher = None
    if cfg.dispatch.enabled and cfg.agents:
        dispatcher = HeuristicDispatcher(
            dispatch_patterns=cfg.dispatch.patterns or None,
            local_patterns=cfg.dispatch.local_patterns or None,
            max_tasks=cfg.dispatch.max_tasks,
        )

    router = Router(fast_path_rules=build_default_fast_paths({t.name for t in tools}))
    gate = cfg.build_gate(confirmer=confirmer)
    if auto_approve is not None:
        gate.auto_approve = auto_approve
    harness = AgentHarness(
        provider,
        runtime,
        gate,
        router=router,
        dispatcher=dispatcher,
        config=HarnessConfig(
            max_steps=cfg.settings.max_steps,
            history_turns=cfg.settings.history_turns,
            max_tool_result_chars=cfg.settings.max_tool_result_chars,
            temperature=cfg.model.temperature,
            max_tokens=cfg.model.max_tokens,
        ),
    )
    harness._manager = manager  # type: ignore[attr-defined]  # for status reporting
    return harness


def _cli_confirmer(call, spec: ToolSpec) -> bool:
    args = json.dumps(call.arguments)
    try:
        answer = input(f"  \033[33mallow {call.name}({args})? [y/N]\033[0m ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes")


async def _cmd_chat(cfg: JarvisConfig) -> int:
    harness = await _build_harness(cfg, _cli_confirmer)
    manager: MCPClientManager = harness._manager  # type: ignore[attr-defined]
    print(f"\033[1mJarvis\033[0m — brain={harness.provider.name}" + (f" | workers={list(cfg.agents)}" if cfg.agents else ""))
    print(f"  tools: {len(manager.tools())} from {len(manager._clients)} server(s)")
    if manager.errors:
        for name, err in manager.errors.items():
            print(f"  \033[31mserver '{name}' failed: {err}\033[0m")
    if cfg.policy.read_only_only:
        print("  \033[33mpolicy: read-only mode\033[0m")
    print("  commands: /tools /reset /quit\n")

    try:
        while True:
            try:
                line = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if line in ("/quit", "/exit"):
                break
            if line == "/tools":
                for t in manager.tools():
                    flags = []
                    if t.read_only:
                        flags.append("read-only")
                    if t.destructive:
                        flags.append("destructive")
                    print(f"  {t.name} ({', '.join(flags) or 'write'}) — {t.description}")
                continue
            if line == "/reset":
                harness.history.clear()
                print("  history cleared")
                continue

            cancel = CancelToken()
            task = asyncio.create_task(harness.run(line, cancel=cancel))
            try:
                result = await task
            except KeyboardInterrupt:
                print("\n  \033[33m(barge-in: cancelling)\033[0m")
                cancel.cancel()
                result = await task
            if result.cancelled:
                print("  \033[33m[cancelled]\033[0m")
                continue
            print(f"jarvis> {result.text}")
            if result.denied:
                print(f"  \033[33m[denied: {', '.join(result.denied)}]\033[0m")
            if result.tool_records:
                used = ", ".join(r.call.name for r in result.tool_records)
                print(f"  \033[2m[used: {used} · {result.steps} step(s) · {result.duration_ms:.0f}ms]\033[0m")
    finally:
        await harness.stop()
    return 0


async def _cmd_eval() -> int:
    outcomes = await run_suite()
    passed = sum(1 for o in outcomes if o.passed)
    print(f"\nJarvis Phase 0 eval — {passed}/{len(outcomes)} passed\n")
    for o in outcomes:
        mark = "\033[32mPASS\033[0m" if o.passed else "\033[31mFAIL\033[0m"
        print(f"  [{mark}] {o.name} ({o.duration_ms:.0f}ms)")
        if not o.passed:
            print(f"         {o.detail}")
    return 0 if passed == len(outcomes) else 1


async def _cmd_demo() -> int:
    from jarvis.core.types import LLMResponse, Message, ToolCall
    from jarvis.eval.cases import _with

    runtime = InMemoryToolRuntime()
    for spec, fn in _with("add", "now", "save_note", "delete_note"):
        runtime.register(spec, fn)

    def script(messages: list[Message], tools: list[ToolSpec]) -> LLMResponse:
        if any(m.role == "tool" for m in messages):
            last = next(m for m in reversed(messages) if m.role == "tool")
            body = last.content or ""
            if "<<<TOOL_OUTPUT" in body:
                body = body.split("<<<TOOL_OUTPUT", 1)[1].split("TOOL_OUTPUT>>>", 1)[0].strip()
            return LLMResponse(text=f"The tool returned: {body}")
        if "note" in (messages[-1].content or "").lower():
            return LLMResponse(tool_calls=[ToolCall(id="d1", name="demo.save_note", arguments={"text": "buy milk"})])
        return LLMResponse(tool_calls=[ToolCall(id="d2", name="demo.add", arguments={"a": 2, "b": 3})])

    provider = ScriptedProvider(script)
    gate = PolicyGate(auto_approve=True)
    router = Router(fast_path_rules=build_default_fast_paths({t.name for t in runtime.tools()}))
    harness = AgentHarness(provider, runtime, gate, router=router)
    await harness.start()
    print("\n\033[1mDeterministic demo (no model required)\033[0m")
    for turn in ["add 2 and 3", "save a note", "what time is it?"]:
        result = await harness.run(turn)
        print(f"  you>    {turn}")
        print(f"  jarvis> {result.text}   [{result.steps} step(s)]")
    await harness.stop()
    return 0


async def _cmd_ask(cfg: JarvisConfig, question: str, *, auto_approve: bool, show_trace: bool) -> int:
    harness = await _build_harness(cfg, _cli_confirmer, auto_approve=auto_approve)
    try:
        result = await harness.run(question)
    finally:
        await harness.stop()
    if show_trace:
        for rec in result.tool_records:
            status = "ok" if (rec.result and rec.result.ok) else ("denied" if not rec.allowed else "error")
            print(f"  [tool] {rec.call.name}({json.dumps(rec.call.arguments)}) -> {status}")
    print(result.text)
    if result.denied:
        print(f"[denied: {', '.join(result.denied)}]")
    return 0 if not result.cancelled else 1


async def _cmd_voice(cfg: JarvisConfig, args) -> int:
    from jarvis.stt.whisper_local import FasterWhisperSTT
    from jarvis.tts.kokoro_tts import KokoroTTS
    from jarvis.voice.loop import VoiceConfig, VoiceLoop

    v = cfg.voice
    stt_model = args.stt_model or v.stt_model
    tts_voice = args.voice or v.tts_voice
    barge_in = args.barge_in if args.barge_in is not None else v.barge_in
    greeting = args.greeting if args.greeting is not None else v.greeting
    input_device = args.input_device if args.input_device is not None else v.input_device
    output_device = args.output_device if args.output_device is not None else v.output_device

    harness = await _build_harness(cfg, _cli_confirmer, auto_approve=args.yes)
    print(f"Loading voice models (STT={stt_model}, TTS={v.tts_backend}/{tts_voice}); first run downloads them...")
    stt = FasterWhisperSTT(stt_model, device=v.stt_device, compute_type=v.stt_compute_type)
    if getattr(v, "tts_backend", "kokoro") == "chatterbox":
        try:
            from jarvis.tts.chatterbox_tts import ChatterboxTTS, ensure_chatterbox_server, is_ready

            if ensure_chatterbox_server() is not None or is_ready():
                tts = ChatterboxTTS()
            else:
                tts = KokoroTTS(voice=tts_voice, speed=v.speech_speed)
        except Exception:
            tts = KokoroTTS(voice=tts_voice, speed=v.speech_speed)
    else:
        tts = KokoroTTS(voice=tts_voice, speed=v.speech_speed)
    vcfg = VoiceConfig(
        input_device=input_device,
        output_device=output_device,
        barge_in=barge_in,
        end_silence_ms=v.end_silence_ms,
        vad_aggressiveness=v.vad_aggressiveness,
        tts_voice=tts_voice,
        speech_speed=v.speech_speed,
        greeting=greeting,
    )
    loop = VoiceLoop(harness, stt, tts, config=vcfg)
    try:
        await loop.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        loop.request_stop()
    return 0


def _cmd_devices() -> int:
    from jarvis.audio.capture import list_devices

    print(list_devices())
    return 0


def _cmd_serve(cfg: JarvisConfig, args) -> int:
    from jarvis.web.server import run_server

    run_server(cfg, host=args.host, port=args.port, open_browser=not args.no_open, https=not args.http, streaming=cfg.voice.streaming)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis", description="Local-first MCP agent harness (Phase 0)")
    sub = parser.add_subparsers(dest="command")

    chat = sub.add_parser("chat", help="interactive text REPL against local MCP servers + a local model")
    chat.add_argument("--config", help="path to jarvis.config.json")

    ask = sub.add_parser("ask", help="ask one question and exit (good for scripting/tests)")
    ask.add_argument("question", help="the question / instruction to run")
    ask.add_argument("--config", help="path to jarvis.config.json")
    ask.add_argument("--yes", action="store_true", help="auto-approve side-effecting tools")
    ask.add_argument("--trace", action="store_true", help="print tool calls as they run")

    sub.add_parser("eval", help="run the deterministic Phase 0 eval suite")
    sub.add_parser("demo", help="run a scripted demo with no model or network")

    voice = sub.add_parser("voice", help="full-duplex-ish voice loop: mic -> STT -> harness -> TTS")
    voice.add_argument("--config", help="path to jarvis.config.json")
    voice.add_argument("--yes", action="store_true", help="auto-approve side-effecting tools")
    voice.add_argument("--stt-model", default=None, help="faster-whisper model (default from config: base.en)")
    voice.add_argument("--voice", default=None, help="Kokoro voice (default from config: af_sarah)")
    voice.add_argument("--barge-in", dest="barge_in", action="store_true", default=None, help="interrupt while speaking")
    voice.add_argument("--no-barge-in", dest="barge_in", action="store_false", help="ignore speech while speaking (use with speakers)")
    voice.add_argument("--greeting", default=None, help="spoken greeting on startup")
    voice.add_argument("--input-device", type=int, default=None, help="input device index (see `jarvis devices`)")
    voice.add_argument("--output-device", type=int, default=None, help="output device index")

    sub.add_parser("devices", help="list audio devices")

    serve = sub.add_parser("serve", help="run the local web UI (browser voice + text)")
    serve.add_argument("--config", help="path to jarvis.config.json")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-open", action="store_true", help="do not open the browser automatically")
    serve.add_argument("--http", action="store_true", help="serve plain HTTP (mic will not work off-localhost)")

    args = parser.parse_args(argv)

    if args.command in (None, "eval"):
        return asyncio.run(_cmd_eval())
    if args.command == "demo":
        return asyncio.run(_cmd_demo())
    if args.command == "devices":
        return _cmd_devices()
    if args.command == "serve":
        path = _find_config(args.config)
        if path is None:
            print("No config found. Copy jarvis.config.example.json to jarvis.config.json.", file=sys.stderr)
            return 2
        return _cmd_serve(JarvisConfig.load(path), args)
    if args.command == "ask":
        path = _find_config(args.config)
        if path is None:
            print("No config found. Copy jarvis.config.example.json to jarvis.config.json.", file=sys.stderr)
            return 2
        return asyncio.run(_cmd_ask(JarvisConfig.load(path), args.question, auto_approve=args.yes, show_trace=args.trace))
    if args.command == "voice":
        path = _find_config(args.config)
        if path is None:
            print("No config found. Copy jarvis.config.example.json to jarvis.config.json.", file=sys.stderr)
            return 2
        try:
            return asyncio.run(_cmd_voice(JarvisConfig.load(path), args))
        except KeyboardInterrupt:
            return 0
    if args.command == "chat":
        path = _find_config(args.config)
        if path is None:
            print("No config found. Copy jarvis.config.example.json to jarvis.config.json.", file=sys.stderr)
            return 2
        cfg = JarvisConfig.load(path)
        return asyncio.run(_cmd_chat(cfg))
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
