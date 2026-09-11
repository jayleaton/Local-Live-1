// Jarvis desktop shell.
//
// This is a CLIENT. It loads the UI served by the Jarvis backend and adds a
// window/tray. It does not own voice, models, or tools, and its lifetime is
// independent of the backend: closing the window (or quitting the app) must not
// stop remote browser sessions. The backend runs separately on the host.
//
// Point it somewhere with JARVIS_URL, e.g. the Tailscale HTTPS URL, or leave the
// default for a locally running `jarvis serve`.
const { app, BrowserWindow, Tray, Menu, shell, nativeImage, systemPreferences } = require("electron");
const path = require("path");

const JARVIS_URL = process.env.JARVIS_URL || "http://127.0.0.1:8766";

let win = null;
let tray = null;
let quitting = false;

function createWindow() {
  win = new BrowserWindow({
    width: 420,
    height: 660,
    minWidth: 320,
    minHeight: 420,
    show: false,
    title: "Jarvis",
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
            `<h3>Can't reach Jarvis</h3><p>No backend at <code>${JARVIS_URL}</code>.</p>` +
            `<p>Start it on the host with <code>jarvis serve</code>, or set <code>JARVIS_URL</code>.</p></body>`
        )
    );
  });

  win.once("ready-to-show", () => win.show());

  // Closing the window hides to the tray; the backend keeps serving.
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
  // A 1px placeholder avoids a missing-icon crash; ship a real icon in packaging.
  const icon = nativeImage.createEmpty();
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
  // Ask macOS for microphone access up front so getUserMedia in the UI doesn't
  // silently fail. Denied access is surfaced by the page itself.
  if (process.platform === "darwin") {
    try {
      await systemPreferences.askForMediaAccess("microphone");
    } catch {
      // Older Electron / unsupported platform: ignore.
    }
  }
  createWindow();
  createTray();
  app.on("activate", showWindow);
});

// Keep running when the window closes; explicit Quit ends the app.
app.on("window-all-closed", (e) => e.preventDefault());
app.on("before-quit", () => {
  quitting = true;
});
