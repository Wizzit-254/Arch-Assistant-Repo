const { app, BrowserWindow, nativeImage, session, shell, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");
const http = require("http");
const crypto = require("crypto");
const { spawn } = require("child_process");

const API_PORT = 9224;
const API_HOST = "127.0.0.1";
const TOKEN = crypto.randomBytes(32).toString("hex");
let backendProc = null;

function pingBackend(timeout = 800){
  return new Promise((resolve) => {
    const req = http.get({ host: API_HOST, port: API_PORT, path: "/api/config", timeout, headers: { Authorization: "Bearer " + TOKEN } }, (res) => {
      res.resume();
      if(res.statusCode === 401){
        resolve('unauthorized'); // Backend running but with a different token
      } else {
        resolve(res.statusCode === 200);
      }
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

function killProcessOnPort(port){
  return new Promise((resolve) => {
    try {
      const { exec } = require('child_process');
      exec('netstat -ano', (err, stdout) => {
        if(err || !stdout) { resolve(false); return; }
        const lines = stdout.split('\n');
        for(const line of lines){
          if(line.includes(String(port)) && line.includes('LISTENING')){
            const parts = line.trim().split(/\s+/);
            if(parts.length >= 5){
              const pid = parts[4];
              if(pid && pid !== '0' && pid !== String(process.pid)){
                exec('taskkill /PID ' + pid + ' /F', () => { resolve(true); });
                return;
              }
            }
          }
        }
        resolve(false);
      });
    } catch(e){ resolve(false); }
  });
}

function trySpawn(cmd, args, cwd){
  try {
    const p = spawn(cmd, args, {
      cwd,
      stdio: 'ignore',
      windowsHide: true,
      env: Object.assign({}, process.env, {
        ARCH_API_TOKEN: TOKEN,
        ARCH_APP_DIR: cwd,
      }),
    });
    p.on("error", () => {});
    p.on("exit", () => {
      if(backendProc === p) backendProc = null;
    });
    return p;
  } catch(e){ return null; }
}

function loadIcon(){
  try {
    const p = path.join(__dirname, "Arch-icon.png");
    if(fs.existsSync(p)){
      const img = nativeImage.createFromPath(p);
      if(!img.isEmpty()) return img;
      const buf = fs.readFileSync(p);
      const img2 = nativeImage.createFromBuffer(buf);
      if(!img2.isEmpty()) return img2;
    }
  } catch(e){}
  return null;
}

function resolveAppRoot(){
  const candidates = [];
  if(process.env.PORTABLE_EXECUTABLE_DIR){
    candidates.push(process.env.PORTABLE_EXECUTABLE_DIR);
  }
  if(process.execPath){
    candidates.push(path.dirname(process.execPath));
  }
  if(process.resourcesPath){
    candidates.push(path.dirname(process.resourcesPath));
  }
  candidates.push(__dirname);
  for(const c of candidates){
    if(c && fs.existsSync(path.join(c, "api_server.py"))){
      return c;
    }
  }
  for(const c of candidates){
    if(c && fs.existsSync(path.join(c, "resources", "app.asar"))){
      return c;
    }
  }
  return candidates[0] || __dirname;
}

function startBackend(){
  try {
    const root = resolveAppRoot();
    const script = path.join(root, "api_server.py");
    const tries = [
      ["python",  [script]],
      ["pythonw", [script]],
      ["py",      ["-3", script]],
    ];
    let idx = 0;

    const escalate = () => {
      if(idx < tries.length){
        const [cmd, args] = tries[idx++];
        backendProc = trySpawn(cmd, args, root);
      }
    };

     (async () => {
       const pingResult = await pingBackend();
       if(pingResult === true) return; // already running with our token
       if(pingResult === 'unauthorized'){
         // Stale backend with a different token — kill it and restart
         await killProcessOnPort(API_PORT);
         await new Promise(r => setTimeout(r, 500));
       }
       escalate();
       for(let i = 0; i < 20; i++){
         await new Promise(r => setTimeout(r, 750));
         if(await pingBackend()) return;
         if(!backendProc || backendProc.exitCode !== null) escalate();
       }
     })();
  } catch(e){}
}

function hardenWebContents(wc, win){
  // Never navigate away from the local app
  wc.on("will-navigate", (e) => e.preventDefault());
  wc.setWindowOpenHandler(() => ({ action: "deny" }));
  wc.on("will-attach-webview", (e) => e.preventDefault());
  if(wc.session) wc.session.setPermissionRequestHandler((wc2, permission, cb) => cb(false));
}

function createWindow() {
  const icon = loadIcon();
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    icon,
    backgroundColor: "#0a0a0c",
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
    },
  });
  if(icon) {
    try { win.setIcon(icon); } catch(e){}
  }
  hardenWebContents(win.webContents, win);
  // Block any non-local network traffic from the renderer, but allow localhost API calls
   session.defaultSession.webRequest.onBeforeRequest({ urls: ["http://*/*", "https://*/*"] }, (details, cb) => {
     const u = new URL(details.url);
     const isLocalAPI = u.hostname === API_HOST && u.port === String(API_PORT);
     if(isLocalAPI){ cb({ cancel: false }); return; }
     // Allow localhost on any port (for dev mode)
     const isLocalhost = u.hostname === "localhost" || u.hostname === "127.0.0.1" || u.hostname === "::1";
     cb({ cancel: !isLocalhost });
   });
  win.loadFile("index.html", { query: { token: TOKEN } });
}

app.whenReady().then(() => {
  const gotLock = app.requestSingleInstanceLock();
  if(!gotLock){
    app.quit();
    return;
  }
  app.on("second-instance", () => {
    if(BrowserWindow.getAllWindows().length){
      const w = BrowserWindow.getAllWindows()[0];
      if(w.isMinimized()) w.restore();
      w.focus();
    }
  });
  startBackend();
  createWindow();

  // IPC: Open system app or website
  ipcMain.handle('open-external', async (event, target) => {
    try {
      if(target.match(/^https?:\/\//) || target.match(/^www\./)){
        await shell.openExternal(target.startsWith('http') ? target : 'https://' + target);
        return { ok: true };
      }
      // Try opening as a file path or app
      if(fs.existsSync(target)){
        await shell.openPath(target);
        return { ok: true };
      }
      // Try opening as a system command/app
      const { exec } = require('child_process');
      exec('start "" "' + target + '"', (err) => {
        if(err){ return { ok: false, error: err.message }; }
        return { ok: true };
      });
      return { ok: true, launched: true };
    } catch(e){
      return { ok: false, error: e.message };
    }
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", () => {
  if(backendProc){
    try { backendProc.kill(); } catch(e){}
    backendProc = null;
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
