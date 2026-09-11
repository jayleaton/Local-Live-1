# Running Jarvis (host operations)

## Start / stop

```sh
uv run python -m jarvis serve            # web UI on http://127.0.0.1:8766 (+ WS on :8767)
uv run python -m jarvis serve --port N   # override
kill "$(cat logs/serve.pid)"             # if launched backgrounded
```

The process also auto-starts sidecars when selected:

- **ASR**: `nemo-speech serve` on `:8081` (Nemotron 3.5 streaming). Falls back to
  sherpa-onnx if unavailable.
- **TTS**: Chatterbox sidecar on `:8082` (`.venv-tts`). Falls back to Kokoro.

Sidecars are separate processes with their own environments; stopping the main server
does not stop them. Logs land in `logs/`.

## Remote access (Tailscale, private)

Keep Jarvis on loopback and terminate TLS with Tailscale:

```sh
uv run python -m jarvis serve --host 127.0.0.1 --port 8766 --http --no-open
tailscale serve --bg --yes --https=8443 http://127.0.0.1:8766   # UI (trusted HTTPS)
tailscale serve --bg --yes --https=8444 http://127.0.0.1:8767   # streaming STT WS
```

Then open `https://<machine>.<tailnet>.ts.net:8443` from any tailnet device. The UI
derives the WebSocket URL from the page origin, so no origins are baked in. HTTPS is
required for `getUserMedia` (microphone).

Do not expose a public listener. Do not change machine security settings to make this
work; keep access inside the tailnet.

## Desktop (Electron) vs the host

- The **Electron window is a client**, not the server. Closing it must not stop the
  backend. Run the backend independently (terminal, `launchd`, or a service) so remote
  browser sessions keep working.
- The Electron app can optionally launch/stop the backend for convenience, but the
  backend's lifetime should be independent of the window.

## Power, lid, and clamshell (important)

Remote access requires the **host to be awake and on the network**.

- **Closing the UI window** (browser tab or Electron window): no effect on the backend.
- **Closing the laptop lid**: on macOS this normally puts the machine to **sleep**, which
  suspends the server. No remote access while suspended.
- **Clamshell mode**: with an external display, keyboard, and power connected, a MacBook
  can keep running with the lid closed. This is a user/hardware configuration, not
  something Jarvis sets.
- To keep a Mac awake for a session you may run `caffeinate -s` (system sleep) or
  `caffeinate -i` (idle sleep) manually. Jarvis does **not** change `pmset`/sleep
  settings for you.

**Do not promise access while the host is asleep.** If remote access is required
continuously, the durable options are: a desktop Mac that does not sleep, clamshell mode
with power + external display, or an explicit (user-made) power configuration decision.
