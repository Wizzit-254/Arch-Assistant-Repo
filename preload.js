// Arch Assistant preload bridge (sandbox-safe).
// Exposes ONLY two validated IPC calls to the renderer:
//   window.electronAPI.openUrl(url)   -> opens http(s) URLs in the browser
//   window.electronAPI.introSeen()    -> marks the first-run intro as seen
const { contextBridge, ipcRenderer } = require("electron");

function isWebUrl(u) {
  return typeof u === "string" && /^(https?:\/\/)/i.test(u.trim());
}

try {
  contextBridge.exposeInMainWorld("electronAPI", {
    openUrl: (url) => {
      if (isWebUrl(url)) ipcRenderer.invoke("open-url", url.trim());
    },
    introSeen: () => ipcRenderer.invoke("intro-seen"),
  });
} catch (e) { /* renderer without bridge: openLink() degrades silently */ }
