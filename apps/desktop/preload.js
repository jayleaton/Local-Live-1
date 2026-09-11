// Minimal preload. The UI is the same page the browser gets, so we expose only a
// capability flag; the Electron shell owns no app logic.
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("jarvisShell", { desktop: true });
