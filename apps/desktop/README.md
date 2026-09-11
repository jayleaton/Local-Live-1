# Local-Live-1 desktop (Electron)

The **all-in-one** desktop app. It starts the backend (Python) itself, waits for it,
and loads the UI; the models load at backend startup and stay resident. Quitting the
app stops the backend it started. Closing the window hides to the tray (the app and
backend keep running) — use **Quit** to stop everything.

## Run (dev)

```sh
cd apps/desktop && npm install
npm start
```

On launch it resolves a backend in this order:
1. a bundled runtime (`resources/backend/.venv` — packaged builds),
2. the bundled **`uv`** (`apps/desktop/bin/uv`, staged by CI) → `uv run --extra voice …`,
3. the repo dev venv (`.venv`).

It writes its backend config to the app's user-data dir and starts
`python -m jarvis serve` on the configured port.

## Settings

**Local-Live-1 → Settings…** (also in the tray):

- **Run the backend on this machine** (all-in-one) — on/off.
- **Port** — local backend port.
- **Backend URL** — used when not running locally (e.g. a Tailscale HTTPS URL).
- **Brain** — on-device (Apple Silicon) or API.
- **API key** — optional, stored locally in the app's user-data (never in the repo).

## Package

```sh
npm run dist            # dmg/zip (macOS), nsis/zip (Windows), AppImage (Linux)
```

For all-in-one installers with the backend bundled, use CI
(`.github/workflows/release.yml`): push a `v*` tag and it builds macOS + Windows and
attaches artifacts to the GitHub Release.

## Notes

- Microphone requires a secure context — localhost or the Tailscale HTTPS URL.
- The backend is a separate process owned by the app; it is not a remote service unless
  you point Settings at a remote URL.
- Remote access from other devices: run the backend and expose it with Tailscale
  (`docs/operations/running.md`); set this app's Backend URL to the HTTPS URL.
