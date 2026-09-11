// Preload for the UI and the app's own Settings modal.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jarvisShell", {
  desktop: true,
  saveSettings: (data) => ipcRenderer.send("jarvis-save-settings", data || {}),
  close: () => ipcRenderer.send("jarvis-close-modal"),
});
