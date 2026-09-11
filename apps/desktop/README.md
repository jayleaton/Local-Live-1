# Jarvis desktop (Electron)

A thin shell that loads the UI served by the Jarvis backend. It is a **client**:
closing the window (or quitting the app) does **not** stop the backend, so remote
browser sessions keep working. The backend runs separately on the host.

## Run

```sh
cd apps/desktop
npm install            # installs electron + electron-builder (network, large)
npm start              # loads JARVIS_URL, default http://127.0.0.1:8766

# point at a remote host (e.g. over Tailscale)
JARVIS_URL="https://<machine>.<tailnet>.ts.net:8443" npm start
```

## Package

```sh
npm run dist           # electron-builder → release/ (per OS)
```

## Notes

- The window close button hides to the tray by design (`main.js`), so the app can keep
  running while the host does. Use **Quit** to exit the shell.
- Over Tailscale, use the **HTTPS** URL; the browser/Electron needs a secure context for
  `getUserMedia` (microphone).
- No origins are baked in: the loaded page derives its API/WS URLs from `location`.
- The shell does not manage the backend process. Start `jarvis serve` independently
  (terminal, `launchd`, or a service) so remote access survives the window.
