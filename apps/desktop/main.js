// Local-Live-1 desktop app (all-in-one).
//
// Starts the backend itself and stops it on quit. Backend resolution order:
//   1. bundled standalone Python with deps  (resources/backend/python)   ← packaged
//   2. bundled venv                          (resources/backend/.venv)
//   3. bundled uv                            (resources/backend/bin/uv)  → creates env
//   4. repo dev venv                         (.venv)
//   5. system uv
// Settings cover internals: run-locally, port, remote URL, brain, model base URL/name,
// API key. Works on macOS (on-device MLX), Windows/Linux (API or a local
// OpenAI-compatible server such as llama.cpp/vLLM on an NVIDIA GPU).
const { app, BrowserWindow, Tray, Menu, shell, nativeImage, systemPreferences, ipcMain } = require("electron");
const { spawn, spawnSync } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const isWin = process.platform === "win32";
const isMac = process.platform === "darwin";
const START_TIMEOUT_MS = 600000; // first run may provision deps

let cfg = null;
let backendUrl = "";
let backendProc = null;
let startedByUs = false;
let win = null;
let tray = null;
let quitting = false;

// ---- config ---------------------------------------------------------------

const userConfigPath = () => path.join(app.getPath("userData"), "config.json");
const backendConfigPath = () => path.join(app.getPath("userData"), "jarvis.config.json");
const backendLogPath = () => path.join(app.getPath("userData"), "backend.log");

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
    baseUrl: saved.baseUrl || "",
    model: saved.model || "",
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
const backendDir = () => (app.isPackaged ? path.join(process.resourcesPath, "backend") : REPO_ROOT);

function writeBackendConfig() {
  const bd = backendDir();
  let base = {};
  try {
    base = JSON.parse(fs.readFileSync(path.join(bd, "jarvis.config.example.json"), "utf8"));
  } catch {
    base = {};
  }
  base.response_mode = cfg.brain;
  base.voice = base.voice || {};
  // Nemotron/Chatterbox sidecars are macOS-oriented; the bundled Windows/Linux
  // runtime falls back to sherpa ASR + Kokoro TTS.
  base.voice.streaming_backend = isMac ? "nemotron" : "sherpa";
  base.voice.tts_backend = isMac ? "chatterbox" : "kokoro";
  base.model = base.model || {};
  if (cfg.baseUrl) base.model.base_url = cfg.baseUrl; // e.g. http://127.0.0.1:8080/v1 (llama.cpp/vLLM)
  if (cfg.model) base.model.model = cfg.model;
  if (cfg.apiKey) {
    base.model.api_key = cfg.apiKey;
    if (base.agents && base.agents.worker) base.agents.worker.api_key = cfg.apiKey;
  }
  try {
    fs.writeFileSync(backendConfigPath(), JSON.stringify(base, null, 2));
  } catch {}
}

// ---- backend --------------------------------------------------------------

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

function findPython() {
  const bd = backendDir();
  const cands = isWin
    ? [path.join(bd, "python", "python.exe"), path.join(bd, "python", "bin", "python.exe")]
    : [path.join(bd, "python", "bin", "python3"), path.join(bd, "python", "bin", "python")];
  const venvPy = isWin ? path.join(bd, ".venv", "Scripts", "python.exe") : path.join(bd, ".venv", "bin", "python");
  const devPy = isWin ? path.join(REPO_ROOT, ".venv", "Scripts", "python.exe") : path.join(REPO_ROOT, ".venv", "bin", "python");
  for (const c of [...cands, venvPy, devPy]) if (fs.existsSync(c)) return c;
  return null;
}

function resolveBackend() {
  const bd = backendDir();
  const uvBin = isWin ? path.join(bd, "bin", "uv.exe") : path.join(bd, "bin", "uv");
  const serve = ["-m", "jarvis", "serve", "--host", "127.0.0.1", "--port", String(cfg.port), "--http", "--no-open"];
  const py = findPython();
  if (py) return { cmd: py, args: serve, env: {} };
  const extras = isMac ? ["--extra", "voice", "--extra", "local"] : ["--extra", "voice"];
  if (fs.existsSync(uvBin)) return { cmd: uvBin, args: ["run", ...extras, "--project", bd, "python", ...serve], env: {} };
  return { cmd: "uv", args: ["run", ...extras, "--project", bd, "python", ...serve], env: {} };
}

async function startBackend() {
  if (await reachable(backendUrl)) return true;
  if (!fs.existsSync(backendDir())) return false;
  writeBackendConfig();
  const { cmd, args, env } = resolveBackend();
  const fd = fs.openSync(backendLogPath(), "a");
  try {
    backendProc = spawn(cmd, args, {
      cwd: backendDir(),
      env: {
        ...process.env,
        ...env,
        JARVIS_CONFIG: backendConfigPath(),
        UV_PROJECT_ENVIRONMENT: path.join(app.getPath("userData"), "backend-venv"),
        UV_CACHE_DIR: path.join(app.getPath("userData"), "uv-cache"),
      },
      stdio: ["ignore", fd, fd],
      detached: false,
    });
    startedByUs = true;
  } catch (e) {
    fs.writeSync(fd, `\n[spawn failed] ${cmd} ${args.join(" ")} :: ${e}\n`);
    return false;
  }
  backendProc.on("exit", () => {
    backendProc = null;
  });
  const deadline = Date.now() + START_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (await reachable(backendUrl)) return true;
    if (!backendProc) return false; // died
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

function logTail(n = 1600) {
  try {
    const s = fs.readFileSync(backendLogPath(), "utf8");
    return s.slice(-n);
  } catch {
    return "(no backend log)";
  }
}

// ---- UI -------------------------------------------------------------------

function dataUrl(html) {
  return "data:text/html," + encodeURIComponent(html);
}
function page(body) {
  return (
    `<!doctype html><body style="font:14px -apple-system,system-ui;margin:0;background:#111315;color:#e8eaed">` +
    `<div style="padding:22px">${body}</div></body>`
  );
}
function showLoading() {
  win.loadURL(
    dataUrl(
      page(
        `<h3 style="margin:0 0 8px">Starting Local-Live-1…</h3>` +
          `<p style="color:#9aa0a6">Setting up the backend. The first run may install components and models — this can take a few minutes.</p>`
      )
    )
  );
}
function showError() {
  win.loadURL(
    dataUrl(
      page(
        `<h3 style="margin:0 0 8px">Local-Live-1 couldn't start</h3>` +
          `<p>No backend at <code>${backendUrl}</code>. Open <b>Local-Live-1 → Settings…</b> to set a backend URL, or check the log:</p>` +
          `<pre style="white-space:pre-wrap;background:#0b0d10;border:1px solid #2a2e35;border-radius:8px;padding:10px;font-size:12px;color:#c3c7cc">${logTail()
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")}</pre>`
      )
    )
  );
}
function loadApp() {
  win.loadURL(backendUrl).catch(showError);
}

async function bootUI() {
  if (!cfg.runLocally) return loadApp();
  if (await reachable(backendUrl)) return loadApp();
  showLoading();
  const ok = await startBackend();
  if (ok) loadApp();
  else showError();
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
    width: 500,
    height: 560,
    modal: true,
    parent: win || undefined,
    resizable: false,
    title: "Settings",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true },
  });
  const cur = JSON.stringify(cfg);
  const html = `<!doctype html><html><body style="margin:0;font:13px -apple-system,system-ui;background:#17191d">
  <div style="padding:16px;color:#e8eaed;height:100vh;box-sizing:border-box;overflow:auto">
    <label style="display:flex;gap:8px;align-items:center;margin-bottom:12px"><input id="run" type="checkbox"/> Run the backend on this machine (all-in-one)</label>
    <label style="display:block;font-size:11px;color:#9aa0a6">Port</label>
    <input id="port" style="width:100%;box-sizing:border-box;background:#0f1216;border:1px solid #2a2e35;color:#e8eaed;border-radius:8px;padding:8px;margin:0 0 12px"/>
    <label style="display:block;font-size:11px;color:#9aa0a6">Backend URL (when not local; e.g. Tailscale HTTPS)</label>
    <input id="url" style="width:100%;box-sizing:border-box;background:#0f1216;border:1px solid #2a2e35;color:#e8eaed;border-radius:8px;padding:8px;margin:0 0 12px"/>
    <label style="display:block;font-size:11px;color:#9aa0a6">Brain</label>
    <select id="brain" style="width:100%;box-sizing:border-box;background:#0f1216;border:1px solid #2a2e35;color:#e8eaed;border-radius:8px;padding:8px;margin:0 0 12px">
      <option value="local">On-device (Apple Silicon MLX)</option>
      <option value="api">API / local OpenAI-compatible server</option>
    </select>
    <label style="display:block;font-size:11px;color:#9aa0a6">Model base URL (e.g. http://127.0.0.1:8080/v1 for llama.cpp / vLLM on NVIDIA)</label>
    <input id="baseUrl" placeholder="https://api.deepseek.com" style="width:100%;box-sizing:border-box;background:#0f1216;border:1px solid #2a2e35;color:#e8eaed;border-radius:8px;padding:8px;margin:0 0 12px"/>
    <label style="display:block;font-size:11px;color:#9aa0a6">Model name</label>
    <input id="model" placeholder="deepseek-flash" style="width:100%;box-sizing:border-box;background:#0f1216;border:1px solid #2a2e35;color:#e8eaed;border-radius:8px;padding:8px;margin:0 0 12px"/>
    <label style="display:block;font-size:11px;color:#9aa0a6">API key (optional; stored locally)</label>
    <input id="key" type="password" style="width:100%;box-sizing:border-box;background:#0f1216;border:1px solid #2a2e35;color:#e8eaed;border-radius:8px;padding:8px;margin:0 0 14px"/>
    <div style="display:flex;gap:8px">
      <button id="s" style="flex:1;padding:9px;border:1px solid #2a2e35;background:#232830;color:#e8eaed;border-radius:8px">Save &amp; restart</button>
      <button id="c" style="flex:1;padding:9px;border:1px solid #2a2e35;background:transparent;color:#e8eaed;border-radius:8px">Cancel</button>
    </div>
  </div>
  <script>
    const cur=${cur};
    const g=id=>document.getElementById(id);
    g('run').checked=cur.runLocally; g('port').value=cur.port; g('url').value=cur.url||'';
    g('brain').value=cur.brain; g('baseUrl').value=cur.baseUrl||''; g('model').value=cur.model||''; g('key').value=cur.apiKey||'';
    g('s').onclick=()=>window.jarvisShell.saveSettings({runLocally:g('run').checked,port:parseInt(g('port').value||'8766',10),url:g('url').value.trim(),brain:g('brain').value,baseUrl:g('baseUrl').value.trim(),model:g('model').value.trim(),apiKey:g('key').value});
    g('c').onclick=()=>window.jarvisShell.close();
  </script></body></html>`;
  modal.loadURL(dataUrl(html));
}

// The web UI owns the voice/speech settings (model choice, TTS, brain). Expose
// them from the app menu so users don't have to find the widget's gear first.
function openVoiceSettings() {
  showWindow();
  if (!win || win.isDestroyed()) return;
  const go = () =>
    win.webContents
      .executeJavaScript(
        "try{ (window.jarvisOpenSettings||function(){view('settings');loadSettings();})('speech'); }catch(e){}"
      )
      .catch(() => {});
  if (win.webContents.isLoading()) win.webContents.once("did-finish-load", go);
  else go();
}

function buildMenu() {
  Menu.setApplicationMenu(
    Menu.buildFromTemplate([
      {
        label: "Local-Live-1",
        submenu: [
          { label: "Voice & speech settings…", click: openVoiceSettings },
          { label: "Backend settings…", click: openSettings },
          { label: "Reload", click: () => win && win.reload() },
          { label: "Open backend log", click: () => shell.openPath(backendLogPath()) },
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
        { label: "Voice & speech settings…", click: openVoiceSettings },
        { label: "Backend settings…", click: openSettings },
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
  stopBackend();
  await bootUI();
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
  buildMenu();
  createWindow();
  createTray();
  await bootUI();
  app.on("activate", showWindow);
});

app.on("window-all-closed", (e) => e.preventDefault());
app.on("before-quit", () => {
  quitting = true;
  stopBackend();
});
