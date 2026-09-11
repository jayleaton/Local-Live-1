// Local-Live-1 desktop shell.
//
// A thin CLIENT: it loads the UI served by the backend and adds a window/tray.
// It owns no voice/models/tools. If the backend is local and not running, it
// starts one (detached) so models are warm; closing the window must NOT stop the
// service or remote sessions. On Windows/Linux, point it at a remote backend
// (Tailscale URL) via the "Backend URL…" menu.
const { app, BrowserWindow, Tray, Menu, shell, nativeImage, systemPreferences, ipcMain } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const isWin = process.platform === "win32";

function configPath() {
  return path.join(app.getPath("userData"), "config.json");
}
function loadConfig() {
  try {
    return JSON.parse(fs.readFileSync(configPath(), "utf8"));
  } catch {
    return {};
  }
}
function saveConfig(patch) {
  const next = { ...loadConfig(), ...patch };
  try {
    fs.mkdirSync(path.dirname(configPath()), { recursive: true });
    fs.writeFileSync(configPath(), JSON.stringify(next, null, 2));
  } catch {}
  return next;
}

let backendUrl = process.env.JARVIS_URL || loadConfig().url || "http://127.0.0.1:8766";
let win = null;
let tray = null;
let quitting = false;

function localPort() {
  const m = backendUrl.match(/^https?:\/\/(127\.0\.0\.1|localhost):(\d+)/);
  return m ? m[2] : null;
}

function reachable(url, timeoutMs = 1500) {
  return new Promise((resolve) => {
    try {
      const u = new URL(String(url).replace(/^ws/, "http") + "/health");
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

// Start the backend if it's local and not already running, so models stay warm.
async function ensureBackend() {
  const port = localPort();
  if (!port) return; // remote host: don't manage its lifecycle
  if (await reachable(backendUrl)) return;
  const py = isWin
    ? path.join(REPO_ROOT, ".venv", "Scripts", "python.exe")
    : path.join(REPO_ROOT, ".venv", "bin", "python");
  if (!fs.existsSync(py)) return; // packaged/remote client: rely on JARVIS_URL
  const child = spawn(
    py,
    ["-m", "jarvis", "serve", "--host", "127.0.0.1", "--port", port, "--http", "--no-open"],
    { cwd: REPO_ROOT, detached: true, stdio: "ignore" }
  );
  child.unref();
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    if (await reachable(backendUrl)) return;
    await new Promise((r) => setTimeout(r, 1500));
  }
}

function loadApp() {
  win.loadURL(backendUrl).catch(() => {
    win.loadURL(
      "data:text/html," +
        encodeURIComponent(
          `<body style="font:14px system-ui;padding:24px;background:#111315;color:#e8eaed">` +
            `<h3>Can't reach Local-Live-1</h3><p>No backend at <code>${backendUrl}</code>.</p>` +
            `<p>Use the menu <b>Local-Live-1 &rarr; Backend URL…</b> to point at your host, or start the backend.</p></body>`
        )
    );
  });
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

  loadApp();
  win.once("ready-to-show", () => win.show());
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

function openUrlModal() {
  const modal = new BrowserWindow({
    width: 460,
    height: 190,
    modal: true,
    parent: win || undefined,
    resizable: false,
    title: "Backend URL",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true },
  });
  const html = `<!doctype html><html><body style="margin:0;font:14px -apple-system,system-ui;background:#17191d">
  <div style="padding:16px;background:#17191d;color:#e8eaed;height:100vh;box-sizing:border-box">
    <label style="display:block;font-size:12px;color:#9aa0a6;margin-bottom:6px">Backend URL</label>
    <input id="u" style="width:100%;box-sizing:border-box;background:#0f1216;border:1px solid #2a2e35;color:#e8eaed;border-radius:8px;padding:9px" value="${backendUrl}"/>
    <div style="margin-top:12px;display:flex;gap:8px">
      <button id="s" style="flex:1;padding:8px;border:1px solid #2a2e35;background:#232830;color:#e8eaed;border-radius:8px">Save</button>
      <button id="c" style="flex:1;padding:8px;border:1px solid #2a2e35;background:transparent;color:#e8eaed;border-radius:8px">Cancel</button>
    </div>
    <p style="color:#9aa0a6;font-size:12px;margin:10px 0 0">e.g. https://&lt;machine&gt;.&lt;tailnet&gt;.ts.net:8443</p>
  </div>
  <script>
    const u=document.getElementById('u');
    document.getElementById('s').onclick=()=>window.jarvisShell && window.jarvisShell.setUrl(u.value);
    document.getElementById('c').onclick=()=>window.jarvisShell && window.jarvisShell.close();
  </script></body></html>`;
  modal.loadURL("data:text/html," + encodeURIComponent(html));
}

function buildMenu() {
  Menu.setApplicationMenu(
    Menu.buildFromTemplate([
      {
        label: "Local-Live-1",
        submenu: [
          { label: "Backend URL…", click: openUrlModal },
          { label: "Reload", click: () => win && win.reload() },
          { type: "separator" },
          { role: "quit" },
        ],
      },
      { label: "View", submenu: [{ role: "toggleDevTools" }, { role: "resetZoom" }, { role: "zoomIn" }, { role: "zoomOut" }] },
    ])
  );
}

function createTray() {
  try {
    tray = new Tray(nativeImage.createEmpty());
    tray.setToolTip("Local-Live-1");
    tray.setContextMenu(
      Menu.buildFromTemplate([
        { label: "Show Local-Live-1", click: showWindow },
        { label: "Backend URL…", click: openUrlModal },
        { label: "Reload", click: () => win && win.reload() },
        { type: "separator" },
        { label: "Quit", click: () => { quitting = true; app.quit(); } },
      ])
    );
    tray.on("click", showWindow);
  } catch {}
}

ipcMain.on("jarvis-set-url", (_e, url) => {
  if (typeof url === "string" && url.trim()) {
    backendUrl = url.trim();
    saveConfig({ url: backendUrl });
  }
  const caller = BrowserWindow.getFocusedWindow();
  if (caller && caller !== win) caller.close();
  if (win && !win.isDestroyed()) loadApp();
});
ipcMain.on("jarvis-close-modal", () => {
  const caller = BrowserWindow.getFocusedWindow();
  if (caller && caller !== win) caller.close();
});

app.whenReady().then(async () => {
  if (process.platform === "darwin") {
    try {
      await systemPreferences.askForMediaAccess("microphone");
    } catch {}
  }
  await ensureBackend();
  buildMenu();
  createWindow();
  createTray();
  app.on("activate", showWindow);
});

app.on("window-all-closed", (e) => e.preventDefault());
app.on("before-quit", () => {
  quitting = true;
});
