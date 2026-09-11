# Architecture overview

Jarvis is deliberately small: **one host process owns voice, the on-device LLM, and
the tool harness; clients are thin.** The goal is the smallest model that makes the
behavior unsurprising.

```
browser ─┐
         ├─ HTTP + WebSocket ─► jarvis serve (Python)
Electron ┘                        ├─ audio I/O        (sounddevice / browser mic)
                                  ├─ STT             (faster-whisper; Nemotron sidecar)
                                  ├─ brain (LLM)     (MLX on device; API optional)
                                  ├─ TTS             (Chatterbox sidecar; Kokoro)
                                  ├─ harness         (tools, policy, dispatch, cancel)
                                  └─ MCP clients     (stdio + streamable HTTP)
```

## Dependency boundaries

- **Backend core** (`core, llm, audio, stt, tts, harness, mcp, tools, agents, dispatch,
  policy, router`): no UI or framework imports; importable with **zero optional deps**.
  Heavy runtimes (MLX, torch, ONNX, CUDA stacks) live behind extras or sidecars.
- **Web surface** (`web`): HTTP/WS routes + the served page. Drives the backend only
  through the service/harness; derives host/WS URLs from `location`, never hardcoded.
- **Desktop shell** (`apps/desktop`, Electron): loads the served UI; may manage the
  backend process. Owns no voice/model logic. Closing the window does not stop the host.
- **Sidecars** (`scripts/chatterbox_server.py`, Nemotron via NeMo-Speech.cpp): isolated
  environments; the core degrades gracefully to fallbacks when they are absent.

## Request flow

1. Client streams 16 kHz PCM to the streaming STT WebSocket.
2. On end-of-utterance, the host runs a turn through the harness: fast paths → the
   on-device brain → tool calls (MCP/agents) → a spoken reply.
3. The reply streams back as text deltas plus sentence-by-sentence audio; one cancel
   token covers the LLM, tools, and playback (barge-in).

## Intentional differences from T3 Code

Jarvis borrows T3 Code's *posture* (remote-ready, multi-surface, don't bake origins,
desktop wraps web, thin clients) but not its machinery:

| T3 Code | Jarvis | Why |
|---|---|---|
| TypeScript / Effect, event-sourced server | Python, plain async | Voice + ML ecosystem is Python; no multi-tenant durability need |
| Many coding-agent provider adapters | One voice brain + optional worker agents | Different product |
| Server can be a host for many environments | One host machine | Local-first, single-user |
| Mobile: React Native | Web + Electron | Smaller surface for now |

## Licensing & attribution

Borrowed *ideas* are reimplemented, not copied. If code is ever adapted from T3 Code
(MIT), retain its notice here and in the file header. See `THIRD_PARTY_NOTICES.md`.
