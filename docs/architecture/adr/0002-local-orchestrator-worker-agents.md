# ADR 0002 — Local orchestrator, remote worker agents (API is not a reply fallback)

- **Status:** Accepted
- **Date:** 2026-09-11
- **Supersedes:** the "remote cortex produces the reply" implication of ADR 0001

## Context

An earlier iteration routed turns to DeepSeek to produce the user-facing reply whenever a question looked like it needed knowledge. That is wrong for this product: the voice interaction must stay on-device, and the API exists to run *worker agents* for high-skill tasks — not to generate conversational replies.

The trigger was OpenAI's Agents/Codex announcement: orchestrate and run agents, bring your own sandbox. The insight is that the *orchestrator + voice* belong on the device, while the *workers* can be remote.

## Decision

1. **The on-device model is the agent and the voice.** Every user-facing reply is generated and spoken locally (local LLM + local TTS). It never asks a remote model for a conversational reply.
2. **Remote models are tools, not providers.** They are reached via:
   - **MCP** — worker agents exposed as MCP tools (e.g. the user's existing T3 agent mesh), and
   - a **built-in API agent tool** — an OpenAI-compatible worker endpoint (e.g. DeepSeek) for agents not behind MCP.
3. **Dispatch is a separate step.** A lightweight planner decides, per turn, `local` vs `dispatch`, and composes the larger, self-contained task prompt that is sent to the worker agent. The local model does not do native function calling for this.
4. **The worker's result is relayed by the local model**, spoken as a short, speech-friendly summary. The full result remains available outside the spoken channel.
5. **Spoken output is filtered** (`to_speech_text`): code blocks, file paths, markdown, and links are stripped before TTS, so Jarvis never reads code aloud.

## Consequences

**Positive**
- Voice is 100% local; the API is only used when a task genuinely needs a worker.
- Worker agents are swappable (MCP or API) and governed by the same policy gate/audit as any tool.
- "Local model talks, planner dispatches" keeps the small model's job simple and reliable.

**Negative / costs**
- The dispatch heuristic can misclassify; needs tuning or an LLM planner for ambiguous requests.
- Two brains (conversation + planner) and an extra hop add a little latency on dispatched turns.
- For voice, the relay is only as speech-friendly as the worker's result; the filter mitigates but can lose nuance.

## Rejected alternatives

- **Remote reply provider with escalation** (previous iteration): violates "voice stays local".
- **Local native function calling for dispatch**: less reliable on 1–4B models; the user chose a separate dispatch step.
- **MCP-only agents**: no path for agents not yet behind MCP.

## Follow-ups

- Optional LLM-based dispatcher that emits `{mode, tool, task}` JSON for better accuracy than regex.
- Surface worker artifacts (diffs, files) in a non-spoken channel.
- Conversation shell (Moshi/PersonaPlex) in front of the local LLM for feel (Phase 2).
