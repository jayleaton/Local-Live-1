# ADR 0001 — Split-Brain Architecture (Conversation Shell + Tool Cortex)

- **Status:** Proposed (partly superseded by [ADR 0002](0002-local-orchestrator-worker-agents.md))
- **Date:** 2026-09-11
- **Deciders:** Jarvis project

> **Update:** the "Tool Cortex" must be **on-device** too. Remote models are not a reply provider; they are worker agents invoked as tools by a separate dispatch step. See ADR 0002.

## Context

We want a fully local, on-device voice agent ("Jarvis") that:
- feels like a natural, interruptible conversation (OpenAI-realtime-like "cut-in"), and
- can call tools via MCP, hit APIs, and offload heavy work to cloud models or other devices.

A single 7B full-duplex model is excellent at natural conversation but weak at tool calling and reasoning. A single larger local model is good at tools but too slow to own turn-taking. Asking one model to do both forces a bad trade-off on the core UX.

## Decision

Adopt a **split-brain** architecture with two cooperating roles behind a shared harness:

1. **Conversation Shell (System 1)** — a small, low-latency, always-listening component (full-duplex model such as Moshi/PersonaPlex *or* a fast streaming small LLM on a cascade). Owns turn-taking, barge-in, backchannel, prosody, and direct replies. Its tool surface is minimal: answer directly or hand off.
2. **Tool Cortex (System 2)** — a 4–32B tool-calling LLM, local by default (llama.cpp/MLX/Ollama) and offloadable to cloud or a second device. Owns tool calls, planning, RAG, and multi-step reasoning.

A model-agnostic **harness** owns session state, routing, the policy/permission gate, context building, MCP client management, memory, and cancellation.

## Consequences

**Positive**
- Keeps voice-to-voice latency low without sacrificing tool capability.
- Clean seam for local/cloud/device offload: the cortex is just a provider.
- Lets us start cascaded (reliable) and add duplex later without re-architecting.
- MCP-native: the harness is another node in the user's existing T3 MCP mesh.

**Negative / costs**
- Two models in memory; more moving parts and more failure modes.
- Handoff quality between shell and cortex becomes a tuning surface.
- Requires a real event/cancellation bus so barge-in stops *all* in-flight work.

**Neutral**
- We are not building a frontier model; we are building a harness. Model picks are swappable and must be re-evaluated on every quant/runtime change.

## Alternatives considered

- **Single duplex model does everything.** Rejected: tool/reasoning quality too low at 7–9B.
- **Single cascaded pipeline, no duplex shell.** Viable v1; rejected as the end state because turn-taking/model-swap-for-latency is weaker than a dedicated shell.
- **Browser/WebGPU only.** Rejected: not hard-real-time, limited models.

## Follow-ups

- Define the event bus and end-to-end cancellation contract (`cancel` propagates to TTS, LLM generation, and MCP calls).
- Build the Phase 0 text harness + deterministic tool eval before any voice work.
- Benchmark shell options (Moshi/PersonaPlex vs fast small LLM cascade) on the reference hardware.

See `docs/research/2026-09-local-voice-jarvis.md` for the full analysis.
