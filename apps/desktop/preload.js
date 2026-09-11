// Minimal preload. The UI is the same page the browser gets. We expose only the
// small shell capabilities (set/clear backend URL) used by the app's own modal.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jarvisShell", {
  desktop: true,
  setUrl: (url) => ipcRenderer.send("jarvis-set-url", String(url || "")),
  close: () => ipcRenderer.send("jarvis-close-modal"),
});
