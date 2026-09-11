# Phase 1 — Local Voice Loop

Goal: a working voice conversation where the **voice and the brain are on-device**, and remote models are only worker agents the dispatcher calls.

## Stack (all local except worker agents)

| Layer | Choice | Why | Measured on M4 Pro |
|---|---|---|---|
| Capture | `sounddevice` (PortAudio), 16 kHz mono int16, 30 ms frames | no deps, reliable on macOS | — |
| VAD / segment | `webrtcvad`, 3-frame onset, 700 ms trailing silence | tiny, no model | <1 ms/frame |
| STT | `faster-whisper` `base.en`, CPU int8 (CTranslate2, no torch) | dependable, fast | ~0.09 RTF |
| Brain (voice) | `MLXProvider` `Qwen2.5-3B-Instruct-4bit`, Metal | on-device replies; 3B 4-bit is fast | ~0.3 s/reply after load |
| TTS | `kokoro-onnx` (82M, Apache-2.0), sentence-streamed | best quality/weight ratio | ~0.18 RTF |
| Workers | MCP tools + built-in `APIAgent` (DeepSeek) | high-skill tasks only | network-bound |

## Turn flow

```
mic frames ─▶ VadSegmenter ──(utterance complete)──▶ FasterWhisperSTT
                                                          │ text
                                                          ▼
        LOCAL MODEL ◀── separate dispatch step ─────────────────────┐
        (always replies)  │                                          │
                          │ local intent            dispatch: compose a larger
                          ▼                          task prompt ─▶ worker agent
                   KokoroTTS ◀── relay result ◀── (MCP tools / APIAgent)
                          │
                          ▼
              Speaker.play(chunk, cancel=token)
```

- The local model answers conversational turns directly. No API involved.
- The dispatcher decides `local` vs `dispatch` and, on dispatch, composes a self-contained task prompt sent to a worker agent. The worker's result comes back and the local model **relays** it.
- One `CancelToken` per turn covers the local model call, the worker call, and TTS playback, so barge-in stops everything.

## Speech-friendly output

`to_speech_text` strips fenced code blocks, inline code, markdown, links, and lists before TTS. The harness also instructs the local model to reply in at most two spoken sentences and never read code aloud. This keeps code-heavy worker results from being spoken verbatim.

## What is deliberately not here yet

- **AEC.** Without it, speaker output can self-trigger barge-in. Headphones with `barge_in: true`, or `--no-barge-in`.
- **Streaming.** The local model generates the full reply before TTS starts; a token/SSE stream would start audio sooner.
- **LLM dispatcher.** Dispatch is heuristic (regex patterns); an LLM planner would handle ambiguous requests better.
- **Duplex shell.** Moshi/PersonaPlex in front of the local model for feel is Phase 2.
- **Wake word.** Always-listening after start; Ctrl-C to stop.

## Commands & tests

```sh
uv sync --extra voice --extra local
uv run python -m jarvis devices
uv run python -m jarvis voice
uv run python -m jarvis ask "Write a python function to reverse a string" --yes --trace
```

- `tests/test_voice_loop.py` — turn + barge-in cancellation (fake STT/TTS/speaker).
- `tests/test_dispatch.py` — dispatcher decisions, agent runtime, harness dispatch → relay.
- `tests/test_voice_integration.py` — real Kokoro → Whisper round-trip, gated by `JARVIS_VOICE_IT=1`.

## Next (Phase 2)

Token-streamed local replies and TTS; optional LLM dispatcher; duplex conversation shell; AEC for speaker-mode barge-in.
