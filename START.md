# START — agent bootstrap

**Local-Live-1** is a local-first voice agent (backend: Python; UI: web + Electron).
This file is for an **AI coding agent** setting it up on a new machine. Copy the
prompt below, then follow the checklist if the agent gets stuck. Read `AGENTS.md`
and `README.md` for architecture and conventions.

---

## Paste this prompt

> Set up **Local-Live-1** on this machine. Work autonomously; only ask if a value is
> genuinely required (API keys, backend URL).
>
> 1. Read `AGENTS.md` and `README.md`.
> 2. Detect the OS/arch. Note: the on-device brain uses **MLX, which is Apple
>    Silicon only**. On Windows/Linux use the **API brain** (DeepSeek) instead.
> 3. Install `uv` if missing (https://docs.astral.sh/uv/).
> 4. Core: `uv sync --extra dev` then `uv run --extra dev pytest` — must pass before
>    continuing.
> 5. Voice: `uv sync --extra voice`. Optional Nemotron streaming ASR via
>    NeMo-Speech.cpp (see `docs/operations/running.md`); optional Chatterbox TTS
>    sidecar in `.venv-tts` (`scripts/chatterbox_server.py`).
> 6. Apple Silicon only: `uv sync --extra local` for the on-device brain.
> 7. Config: `cp jarvis.config.example.json jarvis.config.json`. Put secrets in
>    **environment variables referenced by `${VAR}` / `api_key_env`** — never inline
>    a key in a tracked file. Set `response_mode` to `local` (Apple Silicon) or `api`.
> 8. Run: `uv run python -m jarvis serve`. Confirm `http://127.0.0.1:8766/health`
>    returns `{"ok": true}` and the UI loads.
> 9. Microphone requires a **secure context**: `http://127.0.0.1` or HTTPS. For remote
>    use, expose with Tailscale (`tailscale serve --bg --yes --https=8443 http://127.0.0.1:8766`
>    and `--https=8444 http://127.0.0.1:8767`). Never expose a public listener.
> 10. Report the exact commands run, the chosen brain, any missing system packages,
>     and whether the mic worked. Do **not** change OS sleep/security settings.

---

## Checklist

### Systems
- **Apple Silicon (macOS):** on-device brain via MLX (`--extra local`); Nemotron ASR
  and Chatterbox TTS sidecars work. Recommended path.
- **Windows / Linux:** use the **API brain** (`response_mode: "api"`, `DEEPSEEK_API_KEY`).
  Desktop shell is cross-platform; backend is Python. MLX is unavailable here.

### Requirements
- Python 3.11+ and `uv`. Node 20+ only for the desktop app.
- Optional: Tailscale for private remote access; NeMo-Speech.cpp for Nemotron ASR.

### Desktop app
```sh
cd apps/desktop && npm install
JARVIS_URL="http://127.0.0.1:8766" npm start
# remote backend:
JARVIS_URL="https://<machine>.<tailnet>.ts.net:8443" npm start
```
The window is a client; closing it must not stop the backend. If `JARVIS_URL` is a
local address and no backend is running, the app starts one (detached).

### Model lifecycle
`jarvis serve` **loads and holds** the models at startup (warmup) so turns are fast;
it does not load per request. On Windows/Linux with the API brain there is no local
LLM to warm.

### Verify
- `uv run --extra dev pytest` passes.
- `GET /health` → `{"ok": true}`; `GET /settings` lists the brain and connected tools.
- Ask the agent: *"Report the connected MCP servers"* → it should call
  `system.mcp_status` (and `t3.*` tools if the T3 workspace MCP is running).
- Mic: served over `https://` (or localhost) and OS mic permission granted.

### Don't
- Don't commit weights, `jarvis.config.json`, `logs/`, or secrets.
- Don't modify sleep/security settings; document the lid/sleep behavior instead
  (`docs/operations/running.md`).
- Don't `pkill`/`pgrep | kill`; kill only PIDs you started.
