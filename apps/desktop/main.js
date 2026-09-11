// Local-Live-1 desktop app.
//
// All-in-one: the app starts the backend itself (bundled runtime if present, else
// the dev venv, else `uv`) and stops it when the app quits. The models load at
// backend startup and stay resident. Remote access can still be enabled, and
// internals (port, brain, API key) live in Settings.
const { app, BrowserWindow, Tray, Menu, shell, nativeImage, systemPreferences, ipcMain } = require("electron");
const { spawn, spawnSync } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const isWin = process.platform === "win32";
const isMac = process.platform === "darwin";

let cfg = null; // { runLocally, port, url, brain, apiKey }
let backendUrl = "";
let backendProc = null;
let startedByUs = false;
let win = null;
let tray = null;
let quitting = false;

// ---- config ---------------------------------------------------------------

function userConfigPath() {
  return path.join(app.getPath("userData"), "config.json");
}
function backendConfigPath() {
  return path.join(app.getPath("userData"), "jarvis.config.json");
}
function loadConfig() {
  let saved = {};
  try {
    saved = JSON.parse(fs.readFileSync(userConfigPath(), "utf8"));
  } catch {}
  return {
    runLocally: process.env.JARVIS_URL ? false : saved.runLocally !== false,
    port: saved.port || 8766,
    url: process.env.JARVIS_URL || saved.url || "",
    brain: saved.brain || (isMac ? "local" : "api"),
    apiKey: saved.apiKey || "",
  };
}
function saveConfig() {
  try {
    fs.mkdirSync(path.dirname(userConfigPath()), { recursive: true });
    fs.writeFileSync(userConfigPath(), JSON.stringify(cfg, null, 2));
  } catch {}
}
function refreshBackendUrl() {
  backendUrl = cfg.runLocally ? `http://127.0.0.1:${cfg.port}` : cfg.url || `http://127.0.0.1:${cfg.port}`;
}
function backendDir() {
  return app.isPackaged ? path.join(process.resourcesPath, "backend") : REPO_ROOT;
}

function writeBackendConfig() {
  const bd = backendDir();
  let base = {};
  try {
    base = JSON.parse(fs.readFileSync(path.join(bd, "jarvis.config.example.json"), "utf8"));
  } catch {
    base = {};
  }
  base.response_mode = cfg.brain;
  if (cfg.apiKey) {
    base.model = base.model || {};
    base.model.api_key = cfg.apiKey;
    if (base.agents && base.agents.worker) base.agents.worker.api_key = cfg.apiKey;
  }
  try {
    fs.writeFileSync(backendConfigPath(), JSON.stringify(base, null, 2));
  } catch {}
}

// ---- backend process ------------------------------------------------------

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

function resolveBackend() {
  const bd = backendDir();
  const venvPy = isWin ? path.join(bd, ".venv", "Scripts", "python.exe") : path.join(bd, ".venv", "bin", "python");
  const uvBin = isWin ? path.join(bd, "bin", "uv.exe") : path.join(bd, "bin", "uv");
  const devPy = isWin ? path.join(REPO_ROOT, ".venv", "Scripts", "python.exe") : path.join(REPO_ROOT, ".venv", "bin", "python");
  const serve = ["-m", "jarvis", "serve", "--host", "127.0.0.1", "--port", String(cfg.port), "--http", "--no-open"];
  const extras = isMac ? ["--extra", "voice", "--extra", "local"] : ["--extra", "voice"];
  if (fs.existsSync(venvPy)) return { cmd: venvPy, args: serve, env: { PYTHONPATH: path.join(bd, "src") } };
  if (fs.existsSync(uvBin)) return { cmd: uvBin, args: ["run", ...extras, "--project", bd, "python", ...serve], env: {} };
  if (fs.existsSync(devPy)) return { cmd: devPy, args: serve, env: { PYTHONPATH: path.join(REPO_ROOT, "src") } };
  return { cmd: "uv", args: ["run", ...extras, "--project", bd, "python", ...serve], env: {} };
}

async function startBackend() {
  if (!cfg.runLocally) return true;
  if (await reachable(backendUrl)) return true;
  if (!fs.existsSync(backendDir())) return false;
  writeBackendConfig();
  const { cmd, args, env } = resolveBackend();
  try {
    backendProc = spawn(cmd, args, {
      cwd: backendDir(),
      env: {
        ...process.env,
        ...env,
        JARVIS_CONFIG: backendConfigPath(),
        // Keep any uv-created environment/cache writable (app resources may be read-only).
        UV_PROJECT_ENVIRONMENT: path.join(app.getPath("userData"), "backend-venv"),
        UV_CACHE_DIR: path.join(app.getPath("userData"), "uv-cache"),
      },
      stdio: "ignore",
      detached: false,
    });
    startedByUs = true;
  } catch {
    return false;
  }
  backendProc.on("exit", () => {
    backendProc = null;
  });
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    if (await reachable(backendUrl)) return true;
    if (!backendProc) return false; // process died
    await new Promise((r) => setTimeout(r, 1500));
  }
  return false;
}

function stopBackend() {
  if (!startedByUs || !backendProc) return;
  try {
    if (isWin) spawnSync("taskkill", ["/pid", String(backendProc.pid), "/T", "/F"]);
    else backendProc.kill("SIGTERM");
  } catch {}
  backendProc = null;
  startedByUs = false;
}

async function restartBackend() {
  stopBackend();
  if (win && !win.isDestroyed()) await startBackend();
}

// ---- window / UI ----------------------------------------------------------

function loadApp() {
  win.loadURL(backendUrl).catch(() => {
    win.loadURL(
      "data:text/html," +
        encodeURIComponent(
          `<body style="font:14px system-ui;padding:24px;background:#111315;color:#e8eaed">` +
            `<h3>Local-Live-1 couldn't start</h3><p>No backend at <code>${backendUrl}</code>.</p>` +
            `<p>Open <b>Local-Live-1 &rarr; Settings…</b> to set the backend URL, or ensure a Python/uv runtime is available.</p></body>`
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
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false },
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

function openSettings() {
  const modal = new BrowserWindow({
    width: 480,
    height: 430,
    modal: true,
    parent: win || undefined,
    resizable: false,
    title: "Settings",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true },
  });
  const prefill = JSON.stringify(cfg);
  const html = `<!doctype html><html><body style="margin:0;font:13px -apple-system,system-ui;background:#17191d">
  <div style="padding:16px;color:#e8eaed;height:100vh;box-sizing:border-box;overflow:auto">
    <label style="display:flex;gap:8px;align-items:center;margin-bottom:12px"><input id="run" type="checkbox"/> Run the backend on this machine (all-in-one)</label>
    <label style="display:block;font-size:11px;color:#9aa0a6;margin-bottom:4px">Port</label>
    <input id="port" style="width:100%;box-sizing:border-box;background:#0f1216;border:1px solid #2a2e35;color:#e8eaed;border-radius:8px;padding:8px;margin-bottom:12px"/>
    <label style="display:block;font-size:11px;color:#9aa0a6;margin-bottom:4px">Backend URL (when not running locally, e.g. Tailscale HTTPS)</label>
    <input id="url" style="width:100%;box-sizing:border-box;background:#0f1216;border:1px solid #2a2e35;color:#e8eaed;border-radius:8px;padding:8px;margin-bottom:12px"/>
    <label style="display:block;font-size:11px;color:#9aa0a6;margin-bottom:4px">Brain</label>
    <select id="brain" style="width:100%;box-sizing:border-box;background:#0f1216;border:1px solid #2a2e35;color:#e8eaed;border-radius:8px;padding:8px;margin-bottom:12px">
      <option value="local">On-device (Apple Silicon)</option><option value="api">API</option></select>
    <label style="display:block;font-size:11px;color:#9aa0a6;margin-bottom:4px">API key (optional; stored locally)</label>
    <input id="key" type="password" style="width:100%;box-sizing:border-box;background:#0f1216;border:1px solid #2a2e35;color:#e8eaed;border-radius:8px;padding:8px;margin-bottom:14px"/>
    <div style="display:flex;gap:8px">
      <button id="s" style="flex:1;padding:9px;border:1px solid #2a2e35;background:#232830;color:#e8eaed;border-radius:8px">Save &amp; restart</button>
      <button id="c" style="flex:1;padding:9px;border:1px solid #2a2e35;background:transparent;color:#e8eaed;border-radius:8px">Cancel</button>
    </div>
  </div>
  <script>
    const cur=${prefill};
    const run=document.getElementById('run'), port=document.getElementById('port'), url=document.getElementById('url'), brain=document.getElementById('brain'), key=document.getElementById('key');
    run.checked=cur.runLocally; port.value=cur.port; url.value=cur.url||''; brain.value=cur.brain; key.value=cur.apiKey||'';
    document.getElementById('s').onclick=()=>window.jarvisShell.saveSettings({runLocally:run.checked,port:parseInt(port.value||'8766',10),url:url.value.trim(),brain:brain.value,apiKey:key.value});
    document.getElementById('c').onclick=()=>window.jarvisShell.close();
  </script></body></html>`;
  modal.loadURL("data:text/html," + encodeURIComponent(html));
}

function buildMenu() {
  Menu.setApplicationMenu(
    Menu.buildFromTemplate([
      {
        label: "Local-Live-1",
        submenu: [
          { label: "Settings…", click: openSettings },
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
        { label: "Settings…", click: openSettings },
        { label: "Reload", click: () => win && win.reload() },
        { type: "separator" },
        { label: "Quit", click: () => { quitting = true; app.quit(); } },
      ])
    );
    tray.on("click", showWindow);
  } catch {}
}

ipcMain.on("jarvis-save-settings", async (_e, data) => {
  cfg = { ...cfg, ...data };
  saveConfig();
  refreshBackendUrl();
  const caller = BrowserWindow.getFocusedWindow();
  if (caller && caller !== win) caller.close();
  await restartBackend();
  if (win && !win.isDestroyed()) loadApp();
});
ipcMain.on("jarvis-close-modal", () => {
  const caller = BrowserWindow.getFocusedWindow();
  if (caller && caller !== win) caller.close();
});

app.whenReady().then(async () => {
  if (isMac) {
    try {
      await systemPreferences.askForMediaAccess("microphone");
    } catch {}
  }
  cfg = loadConfig();
  refreshBackendUrl();
  const ok = await startBackend();
  if (!ok && cfg.runLocally) {
    // leave backendUrl as-is; loadApp shows the guidance page
  }
  buildMenu();
  createWindow();
  createTray();
  app.on("activate", showWindow);
});

app.on("window-all-closed", (e) => e.preventDefault());
app.on("before-quit", () => {
  quitting = true;
  stopBackend();
});
