# AGENTS.md — Jarvis

Jarvis is a **local-first voice agent**. It listens on one host machine, runs speech
(ASR/TTS) and an on-device LLM, and can call tools over MCP (local files, the T3
workspace, the web). A remote LLM/agent may be used as a *worker* for heavy tasks.
The same UI is served to a browser and wrapped as an Electron desktop app.

This file guides agents and contributors. Treat it as strong defaults, not law;
explain and get sign-off before breaking a rule.

## What Jarvis is (and is not)

- **Is:** a single-host Python backend that owns the microphone, speech models, the
  on-device LLM, the tool/MCP harness, and a small web UI. Voice never leaves the host
  except when a tool explicitly calls out.
- **Is not:** a multi-provider coding agent, an event-sourced orchestration platform,
  or a hosted multi-tenant service. Do not import those patterns wholesale.

## Architecture and dependency boundaries

```
browser (web UI) ─┐
                  ├─ HTTP + WebSocket ─►  jarvis serve (Python, the host)
Electron shell ───┘                          ├─ audio I/O (sounddevice / browser mic)
                                             ├─ STT (faster-whisper, Nemotron sidecar)
                                             ├─ LLM (MLX on device; API optional)
                                             ├─ TTS (Chatterbox sidecar; Kokoro)
                                             ├─ harness (tools, policy, dispatch)
                                             └─ MCP clients (stdio + streamable HTTP)
```

Hard boundaries (do not cross):

- **`src/jarvis/core`, `llm`, `audio`, `stt`, `tts`, `harness`, `mcp`, `tools`, `agents`,
  `dispatch`, `policy`, `router`** — the backend. No UI/framework imports. No knowledge of
  Electron or the browser.
- **`src/jarvis/web`** — the HTTP/WebSocket surface and the served UI. Talks to the backend
  only through the harness/service objects; never drives models directly.
- **`apps/desktop`** (Electron) — a thin shell that loads the served UI and, optionally,
  manages the backend process. It owns no voice/model logic.
- **Model sidecars** (`scripts/chatterbox_server.py`, `nemotron` via NeMo-Speech.cpp) run in
  their own environments to isolate heavy deps (torch, CUDA-oriented stacks). The Python
  core must stay importable without them.

Rules that follow from this:

- Keep the core importable with **no optional dependencies installed** (MLX/torch/ONNX are
  behind extras). `pytest` must pass on core alone.
- New heavy dependency → a new optional extra or sidecar, never a core import.
- The UI talks to the host; it must not hardcode origins. Remote access is via Tailscale
  Serve; TLS terminates there.

## Remote, desktop, and multi-device (learned from T3 Code)

- The desktop window is **not** a server. Closing it must not stop the backend; the backend
  must keep serving browser clients. Power the host down and remote access stops — say so.
- **Never bake origins into the UI.** Serve relative URLs; let the client derive the WS/API
  host from `location`. Baking `localhost` breaks every remote browser.
- Remote access must stay authenticated/private (Tailscale). Do not add a public listener.
- One UI, many surfaces: web and Electron share the same served page. Electron only adds a
  shell, tray, and process lifecycle.

## Keep voice local

- Microphone audio, ASR, TTS, and user-facing replies stay on the host. A remote model may
  be invoked **only** as a tool/worker for a specific task, and its result is relayed by the
  on-device model.
- Preserve barge-in/interruption: one cancel signal must stop LLM, tools, and audio.
- Speech output is capped (`max_spoken_sentences`) and filtered (`to_speech_text`) so code,
  markdown, or long text is never read aloud.

## Working in this repo

- Python 3.11+, `uv` for envs. `uv run --extra dev pytest` for the suite.
- Focused tests over broad runs. Backend behavior changes ship with a test.
- Frontend changes: verify in a real browser (web) and, when asked, Electron. Ask before
  computer use or launching browsers.
- Do not commit generated weights, model caches, `jarvis.config.json`, `logs/`, or any
  secrets. Use `jarvis.config.example.json` with env-var indirection.
- Never `pkill`/`pgrep | kill`. Kill only a PID you captured at spawn.
- Conventional commits. One concern per PR. Never open a PR unless asked.

## Documentation

- `docs/architecture/` — decisions and cross-cutting constraints (see ADRs).
- `docs/operations/` — running the host, Tailscale, power/clamshell, sidecars.
- `docs/user/` — how to use Jarvis.
- `docs/research/` — background analysis (not a spec).
- Prefer code comments for local reasoning; don't narrate control flow in docs.

## Glossary

- **host** — the machine running `jarvis serve` (microphone, models, tools).
- **client** — the web page or the Electron shell.
- **brain** — the model that talks to the user. On-device by default.
- **worker** — a remote agent/model invoked as a tool for heavy tasks.
- **harness** — the loop that turns a turn into tool calls and a spoken reply.
- **sidecar** — a separately-environed process (NeMo ASR, Chatterbox TTS).
- **MCP** — Model Context Protocol; how tools are exposed to the brain.
