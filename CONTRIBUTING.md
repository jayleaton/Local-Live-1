# Contributing

Thanks for helping with Jarvis. It's a local-first voice agent: a Python backend
that owns speech + the on-device LLM + the tool harness, plus a small UI served to
browsers and wrapped for desktop.

## Dev setup

```sh
uv sync --extra dev            # core + tests (no models needed)
uv run --extra dev pytest      # must pass on core alone
```

Optional extras (install only what you need):

```sh
uv sync --extra voice    # sounddevice, faster-whisper, kokoro, sherpa, websockets
uv sync --extra local    # mlx-lm (Apple Silicon on-device LLM)
```

Heavy stacks that need their own environment (isolated on purpose):

- **Nemotron 3.5 streaming ASR** via NeMo-Speech.cpp (see `docs/operations/`).
- **Chatterbox TTS** sidecar in `.venv-tts` (`scripts/chatterbox_server.py`).

## Running

```sh
cp jarvis.config.example.json jarvis.config.json   # then fill env vars, not secrets
uv run python -m jarvis serve                       # web UI at http://127.0.0.1:8766
```

## Guidelines

- Keep the core importable without optional deps; new heavy deps go behind an extra
  or a sidecar. See `AGENTS.md` for the full dependency boundaries.
- Backend behavior changes ship with a focused test. Prefer small, observable tests.
- Don't commit weights, `jarvis.config.json`, `logs/`, or secrets. Use the example
  config with `${ENV_VAR}` indirection.
- Conventional commits, one concern per change. Don't open a PR unless asked.
- Frontend: verify in a real browser once integrated; ask before launching browsers.

## Licensing

Project code is MIT. Third-party models and libraries keep their own licenses; see
`THIRD_PARTY_NOTICES.md`. When adding a dependency or model, note its license there
and prefer permissive/commercial-safe options for anything shipped by default.
