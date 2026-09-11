# Local-Live-1

**Local-Live-1** is a **local-first voice agent** (the assistant is named **Jarvis**).
It runs on your own machine: speech in, speech out, an on-device LLM, and a tool
harness that can call MCP servers (local tools, your T3 workspace, the web). Heavy
tasks can be handed to a remote *worker* agent, but voice and the default brain stay
on-device.

The same simple UI is served to the browser and wrapped as an Electron desktop app.

> **Status:** early / experimental. On-device brain tested on Apple Silicon (MLX);
> streaming ASR via NVIDIA Nemotron 3.5 (NeMo-Speech.cpp); TTS via Chatterbox (default)
> or Kokoro. A remote LLM can be selected as the response brain.

## Highlights

- **Voice stays local.** Microphone audio, ASR, TTS, and (by default) the LLM never
  leave the host. A remote model is only used if you pick the API brain or a tool calls out.
- **Feels responsive.** Streaming partial transcripts, sentence-by-sentence speech, a
  spoken "let me check" before slow tool calls, and barge-in (interrupt any time).
- **Tool-capable.** Native function calling over MCP: local web search/fetch, the T3
  workspace (projects/threads), GitHub repo reading, and a DeepSeek worker agent.
- **One UI, many surfaces.** A flat, minimal light/dark widget served to any browser and
  packaged for desktop. Remote access over Tailscale with trusted HTTPS.
- **Configurable.** Toggle the brain (on-device ⇄ API), the on-device model, the TTS
  engine/voice, and how many sentences are spoken.

## Requirements

- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)
- macOS on Apple Silicon recommended (MLX + Metal). Linux/CUDA also work for parts.
- Optional: [Tailscale](https://tailscale.com/) for private remote access.
- Optional: [NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp) for Nemotron streaming ASR.

## Install

```sh
uv sync --extra dev                 # core + tests (no models)
uv sync --extra voice --extra local # + audio/STT/TTS and the on-device LLM (MLX)
```

Heavy stacks run as isolated sidecars (their own environments):

- **Chatterbox TTS** → `.venv-tts` (`scripts/chatterbox_server.py`), auto-started.
- **Nemotron streaming ASR** → NeMo-Speech.cpp `nemo-speech serve`, auto-started if installed.

## Run

```sh
cp jarvis.config.example.json jarvis.config.json   # then set env vars (never inline secrets)
uv run python -m jarvis serve                       # web UI at http://127.0.0.1:8766
```

Open the UI, press the mic, and talk — it finalizes when you pause and speaks the reply.

### Desktop (Electron)

```sh
cd apps/desktop && npm install
npm start                                           # loads http://127.0.0.1:8766
JARVIS_URL="https://<machine>.<tailnet>.ts.net:8443" npm start   # or point at a remote host
```

The Electron window is a **client**: closing it does not stop the backend, so remote
browser sessions keep working. Run the backend independently.

### Remote access (Tailscale, private)

Keep Jarvis on loopback and terminate TLS with Tailscale (microphones require HTTPS):

```sh
uv run python -m jarvis serve --host 127.0.0.1 --port 8766 --http --no-open
tailscale serve --bg --yes --https=8443 http://127.0.0.1:8766   # UI
tailscale serve --bg --yes --https=8444 http://127.0.0.1:8767   # streaming ASR WebSocket
```

Then open `https://<machine>.<tailnet>.ts.net:8443` from any tailnet device. The UI
derives its WebSocket URL from the page origin, so nothing is baked to localhost.

## Configuration

`jarvis.config.json` (gitignored). Secrets come from env vars via `${VAR}` / `api_key_env`.

```jsonc
{
  "response_mode": "local",                       // local | api
  "local": { "model": "mlx-community/Qwen3.5-9B-MLX-4bit" },
  "model": { "base_url": "https://api.deepseek.com", "model": "deepseek-flash",
             "api_key_env": "DEEPSEEK_API_KEY", "extra_params": { "thinking": { "type": "disabled" } } },
  "agents": { "worker": { "base_url": "https://api.deepseek.com", "model": "deepseek-flash",
                          "api_key_env": "DEEPSEEK_API_KEY", "reasoning_effort": "high" } },
  "voice": { "streaming": true, "streaming_backend": "nemotron", "tts_backend": "chatterbox",
             "tts_voice": "af_heart", "max_spoken_sentences": 3 },
  "policy": { "allowed_servers": ["demo", "t3", "zread", "agent", "webtools"],
              "deny_patterns": ["*shell*", "*exec*"], "auto_approve": false },
  "servers": {
    "demo":   { "command": ["python3", "servers/demo_mcp_server.py"] },
    "t3":     { "url": "http://127.0.0.1:3773/mcp/workspace" },
    "zread":  { "url": "https://api.z.ai/api/mcp/zread/mcp",
                "headers": { "Authorization": "Bearer ${Z_AI_API_KEY}" } }
  }
}
```

Most of this is editable at runtime from the UI's **Settings** panel.

## Models & licensing

Defaults are chosen to be commercially safe where possible. See `THIRD_PARTY_NOTICES.md`.

- **STT:** NVIDIA Nemotron 3.5 ASR Streaming (OpenMDW-1.1) via NeMo-Speech.cpp; fallback sherpa-onnx Zipformer.
- **TTS:** Chatterbox-Turbo (MIT) default; Kokoro-82M (Apache-2.0) fast fallback.
- **Brain:** Qwen3.5 MLX 4-bit (Apache-2.0) on-device; optional DeepSeek API.

## Power & the lid

Remote access needs the **host awake**. Closing the UI window doesn't affect the
backend; closing the laptop **lid** normally suspends it. Clamshell mode (power +
external display) or a non-sleeping desktop can serve continuously — that's a user
configuration, not something Jarvis changes. Jarvis never modifies sleep/security
settings. See `docs/operations/running.md`.

## Project layout

```
src/jarvis/        backend: core, llm, audio, stt, tts, harness, mcp, tools, agents, web
servers/           demo MCP stdio server (tests)
scripts/           sidecars (Chatterbox TTS)
apps/desktop/      Electron shell (thin client)
docs/              architecture, operations, user, research, design
tests/             focused tests (run on core alone)
```

## Testing

```sh
uv run --extra dev pytest       # core suite (no models required)
```

## Contributing

See `CONTRIBUTING.md` and `AGENTS.md`.

## License

MIT — see `LICENSE`. Third-party components keep their own licenses.
