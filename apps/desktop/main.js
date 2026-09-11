// Local-Live-1 desktop shell.
//
// This is a CLIENT. It loads the UI served by the local backend and adds a
// window/tray. It does not own voice, models, or tools. If the backend isn't
// running (and the URL is local), it starts it once and leaves it running
// detached — closing the window must NOT stop the service or remote sessions.
const { app, BrowserWindow, Tray, Menu, shell, nativeImage, systemPreferences } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");

const JARVIS_URL = process.env.JARVIS_URL || "http://127.0.0.1:8766";
const REPO_ROOT = path.resolve(__dirname, "..", "..");

let win = null;
let tray = null;
let quitting = false;

function reachable(url, timeoutMs = 1500) {
  return new Promise((resolve) => {
    try {
      const u = new URL(url.replace(/^ws/, "http") + "/health");
      const req = http.get({ hostname: u.hostname, port: u.port, path: u.pathname, timeout: timeoutMs }, (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      });
      req.on("timeout", () => req.destroy());
      req.on("error", () => resolve(false));
    } catch {
      resolve(false);
    }
  });
}

// Start the backend if it's local and not already running, so models are warm.
async function ensureBackend() {
  const m = JARVIS_URL.match(/^https?:\/\/(127\.0\.0\.1|localhost):(\d+)/);
  if (!m) return; // remote host: don't manage its lifecycle
  if (await reachable(JARVIS_URL)) return;
  const port = m[2];
  const py = path.join(REPO_ROOT, ".venv", "bin", "python");
  const cmd = fs.existsSync(py) ? py : "python3";
  const child = spawn(
    cmd,
    ["-m", "jarvis", "serve", "--host", "127.0.0.1", "--port", port, "--http", "--no-open"],
    { cwd: REPO_ROOT, detached: true, stdio: "ignore" }
  );
  child.unref();
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    if (await reachable(JARVIS_URL)) return;
    await new Promise((r) => setTimeout(r, 1500));
  }
}

function createWindow() {
  win = new BrowserWindow({
    width: 460,
    height: 720,
    minWidth: 340,
    minHeight: 460,
    show: false,
    title: "Local-Live-1",
    backgroundColor: "#111315",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  win.loadURL(JARVIS_URL).catch(() => {
    win.loadURL(
      "data:text/html," +
        encodeURIComponent(
          `<body style="font:14px system-ui;padding:24px;background:#111315;color:#e8eaed">` +
            `<h3>Can't reach Local-Live-1</h3><p>No backend at <code>${JARVIS_URL}</code>.</p>` +
            `<p>Start it with <code>uv run python -m jarvis serve</code>, or set <code>JARVIS_URL</code>.</p></body>`
        )
    );
  });

  win.once("ready-to-show", () => win.show());

  // Closing the window hides to the tray; the backend keeps serving remotely.
  win.on("close", (e) => {
    if (!quitting) {
      e.preventDefault();
      win.hide();
    }
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

function showWindow() {
  if (!win || win.isDestroyed()) createWindow();
  else {
    win.show();
    win.focus();
  }
}

function createTray() {
  const icon = nativeImage.createEmpty(); // ship a real icon in packaging
  try {
    tray = new Tray(icon);
    tray.setToolTip("Local-Live-1");
    tray.setContextMenu(
      Menu.buildFromTemplate([
        { label: "Show Local-Live-1", click: showWindow },
        { label: "Reload", click: () => win && win.reload() },
        { type: "separator" },
        { label: "Quit", click: () => { quitting = true; app.quit(); } },
      ])
    );
    tray.on("click", showWindow);
  } catch {
    // Tray is optional.
  }
}

app.whenReady().then(async () => {
  // Ask macOS for microphone access up front so getUserMedia doesn't silently fail.
  if (process.platform === "darwin") {
    try {
      await systemPreferences.askForMediaAccess("microphone");
    } catch {
      // Older Electron / unsupported platform: ignore.
    }
  }
  await ensureBackend();
  createWindow();
  createTray();
  app.on("activate", showWindow);
});

// Keep running when the window closes; explicit Quit ends the app.
app.on("window-all-closed", (e) => e.preventDefault());
app.on("before-quit", () => {
  quitting = true;
});
