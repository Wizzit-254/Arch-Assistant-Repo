const { app, BrowserWindow, nativeImage, session, shell, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");
const os = require("os");
const http = require("http");
const https = require("https");
const crypto = require("crypto");
const { spawn } = require("child_process");

const API_PORT = 9332;
const API_HOST = "127.0.0.1";
const TOKEN = crypto.randomBytes(32).toString("hex");
let backendProc = null;

// ---- silent runtime bootstrap (portable: fetch missing backend runtimes on first run) ----
// Official sources only. Everything runs hidden (no dialogs); failures are best-effort
// so the app still opens and the backend status UI reports offline instead of hanging.
const RUNTIME_BOOTSTRAP = {
  pythonUrl: "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe",
  vcRedistUrl: "https://aka.ms/vs/17/release/vc_redist.x64.exe",
  pipPackages: [["yt_dlp", "yt-dlp"], ["feedparser", "feedparser"], ["psutil", "psutil"]],
  languagePacks: {
    "sw": "Kiswahili locale support via python-babel",
    "fr": "French locale support via python-babel",
    "zh": "Simplified Chinese locale via python-babel",
    "ja": "Japanese locale via python-babel",
    "ar": "Arabic locale via python-babel",
  },
};
let runtimePython = null; // [cmd, preArgs] once resolved, preferred for backend spawn

function runHidden(cmd, args, timeoutMs, cwd){
  return new Promise((resolve) => {
    let done = false;
    let out = "", err = "";
    let child = null;
    const timer = setTimeout(() => {
      if(!done){ done = true; try { child.kill(); } catch(e){} resolve({ code: -1, stdout: out, stderr: err }); }
    }, timeoutMs || 60000);
    try {
      child = spawn(cmd, args || [], { windowsHide: true, stdio: ["ignore", "pipe", "pipe"], cwd: cwd || undefined });
    } catch(e){ clearTimeout(timer); resolve({ code: -1, stdout: out, stderr: err }); return; }
    if(child.stdout) child.stdout.on("data", (d) => { out += d.toString(); });
    if(child.stderr) child.stderr.on("data", (d) => { err += d.toString(); });
    child.on("error", () => { if(!done){ done = true; clearTimeout(timer); resolve({ code: -1, stdout: out, stderr: err }); } });
    child.on("close", (code) => { if(!done){ done = true; clearTimeout(timer); resolve({ code: code, stdout: out, stderr: err }); } });
  });
}

function downloadFile(url, dest, timeoutMs){
  return new Promise((resolve) => {
    let done = false;
    const finish = (ok) => { if(!done){ done = true; resolve(ok); } };
    const timer = setTimeout(() => finish(false), timeoutMs || 300000);
    const get = (u, redirects) => {
      if(redirects > 5){ clearTimeout(timer); finish(false); return; }
      let lib = null;
      try { lib = u.indexOf("https:") === 0 ? https : http; } catch(e){ clearTimeout(timer); finish(false); return; }
      let req = null;
      try {
        req = lib.get(u, { headers: { "User-Agent": "Arch-Assistant-Bootstrap" } }, (res) => {
          if(res.statusCode >= 300 && res.statusCode < 400 && res.headers.location){
            res.resume();
            let next = res.headers.location;
            try { next = new URL(next, u).toString(); } catch(e){}
            get(next, redirects + 1);
            return;
          }
          if(res.statusCode !== 200){ res.resume(); clearTimeout(timer); finish(false); return; }
          const out = fs.createWriteStream(dest);
          res.pipe(out);
          out.on("finish", () => { out.close(() => { clearTimeout(timer); finish(true); }); });
          out.on("error", () => { clearTimeout(timer); finish(false); });
        });
      } catch(e){ clearTimeout(timer); finish(false); return; }
      req.on("error", () => { clearTimeout(timer); finish(false); });
      req.setTimeout(timeoutMs || 300000, () => { try { req.destroy(); } catch(e){} clearTimeout(timer); finish(false); });
    };
    get(url, 0);
  });
}

function isOnline(timeoutMs){
  // Fast connectivity probe so offline machines skip downloads immediately
  // instead of hanging on long timeouts. Best-effort, never throws.
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if(!done){ done = true; resolve(v); } };
    const timer = setTimeout(() => finish(false), timeoutMs || 5000);
    try {
      const req = https.get("https://pypi.org/simple/", { headers: { "User-Agent": "Arch-Assistant-Bootstrap" } }, (res) => {
        res.resume();
        clearTimeout(timer);
        finish(res.statusCode < 500);
      });
      req.on("error", () => { clearTimeout(timer); finish(false); });
      req.setTimeout(timeoutMs || 5000, () => { try { req.destroy(); } catch(e){} clearTimeout(timer); finish(false); });
    } catch(e){ clearTimeout(timer); finish(false); }
  });
}

async function commandExists(cmd){  try {
    const r = await runHidden("where", [cmd], 8000);
    return r.code === 0 && r.stdout.trim().length > 0;
  } catch(e){ return false; }
}

async function pythonWorks(cmd, preArgs){
  try {
    const r = await runHidden(cmd, [...(preArgs || []), "-c", "import sys"], 15000);
    return r.code === 0;
  } catch(e){ return false; }
}

async function resolvePython(){
  try {
    if(runtimePython){
      const [rc, rp] = runtimePython;
      if(await pythonWorks(rc, rp)) return runtimePython;
      runtimePython = null;
    }
    const localApp = process.env.LOCALAPPDATA || "";
    const progFiles = process.env.ProgramFiles || "C:\\Program Files";
    const candidates = [];
    if(localApp) candidates.push([path.join(localApp, "Programs", "Python", "Python312", "python.exe"), []]);
    if(progFiles) candidates.push([path.join(progFiles, "Python312", "python.exe"), []]);
    for(const [exe, pre] of candidates){
      try { if(exe && fs.existsSync(exe) && await pythonWorks(exe, pre)) return [exe, pre]; } catch(e){}
    }
    if(await commandExists("python")){
      try {
        const v = await runHidden("python", ["-c", "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)"], 15000);
        if(v.code === 0) return ["python", []];
      } catch(e){}
    }
    if(await commandExists("py")){
      if(await pythonWorks("py", ["-3"])) return ["py", ["-3"]];
    }
    return null;
  } catch(e){ return null; }
}

async function ensurePython(online){
  try {
    let found = await resolvePython();
    if(found){ runtimePython = found; return found; }
    if(!online) return null; // offline: can't fetch, don't hang
    // Silently install official Python per-user (no admin, no PATH change, no UI)
    const tmp = process.env.TEMP || process.env.TMP || os.tmpdir();
    const installer = path.join(tmp, "arch-python-setup.exe");
    try {
      if(!fs.existsSync(installer)){
        const ok = await downloadFile(RUNTIME_BOOTSTRAP.pythonUrl, installer, 300000);
        if(!ok) return null;
      }
    } catch(e){ return null; }
    await runHidden(installer, ["/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_pip=1", "Include_test=0"], 360000);
    found = await resolvePython();
    if(found){ runtimePython = found; return found; }
    return null;
  } catch(e){ return null; }
}

async function ensurePipPackages(py, online){
  if(!py || !online) return;
  const [cmd, pre] = py;
  for(const [mod, pkg] of RUNTIME_BOOTSTRAP.pipPackages){
    try {
      const chk = await runHidden(cmd, [...pre, "-c", "import " + mod], 20000);
      if(chk.code === 0) continue;
      await runHidden(cmd, [...pre, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", pkg], 240000);
    } catch(e){}
  }
}

async function ensurePythonLanguages(py, online){
  if(!py || !online) return;
  const [cmd, pre] = py;
  try {
    const chk = await runHidden(cmd, [...pre, "-c", "import babel; babel.Locale('en')"], 20000);
    if(chk.code === 0) return; // babel already available
    await runHidden(cmd, [...pre, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "babel"], 240000);
    for(const langCode of Object.keys(RUNTIME_BOOTSTRAP.languagePacks)){
      try {
        await runHidden(cmd, [...pre, "-c", `import babel; babel.Locale('${langCode}')`], 15000);
      } catch(e){}
    }
  } catch(e){}
}

function setBootstrapStatus(msg, win){
  try {
    win.webContents.executeJavaScript(
      `window._bootstrapStatus && window._bootstrapStatus('${msg}')`
    );
  } catch(e){}
}

async function ensureRuntimes(win){
  // Best-effort and silent: never throws, so the app always opens.
  try {
    const online = await isOnline();
    if(win) setBootstrapStatus("Downloading backend runtimes...", win);
    const py = await ensurePython(online);
    if(win) setBootstrapStatus("Installing Python packages (yt-dlp, feedparser, psutil)...", win);
    if(py) await ensurePipPackages(py, online);
    if(win) setBootstrapStatus("Downloading language packs (Kiswahili, French, Chinese, Japanese, Arabic)...", win);
    if(py) await ensurePythonLanguages(py, online);
    if(win) setBootstrapStatus("Finalizing VC++ runtime...", win);
    await ensureVCRuntime(online);
    if(win) setBootstrapStatus("Ready", win);
  } catch(e){
    if(win) setBootstrapStatus("Offline mode", win);
  }
}

async function ensureVCRuntime(online){
  try {
    const sysRoot = process.env.SystemRoot || "C:\\Windows";
    const dlls = [path.join(sysRoot, "System32", "vcruntime140.dll"), path.join(sysRoot, "System32", "ucrtbase.dll")];
    const present = () => dlls.every((d) => { try { return fs.existsSync(d); } catch(e){ return false; } });
    if(present()) return true;
    if(!online) return false;
    const tmp = process.env.TEMP || process.env.TMP || os.tmpdir();
    const exe = path.join(tmp, "arch-vc-redist.exe");
    try {
      if(!fs.existsSync(exe)){
        const ok = await downloadFile(RUNTIME_BOOTSTRAP.vcRedistUrl, exe, 300000);
        if(!ok) return false;
      }
    } catch(e){ return false; }
    await runHidden(exe, ["/quiet", "/norestart"], 360000);
    return present();
  } catch(e){ return false; }
}

function pingBackend(timeout = 400){
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
      const child = spawn('netstat', ['-ano'], { windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] });
      let stdout = '';
      child.stdout.on('data', (d) => stdout += d.toString());
      child.on('close', () => {
        const lines = stdout.split('\n');
        let killed = 0;
        const pidsToKill = new Set();
        for(const line of lines){
          if(line.includes(String(port)) && line.includes('LISTENING')){
            const parts = line.trim().split(/\s+/);
            if(parts.length >= 5){
              const pid = parts[4];
              if(pid && pid !== '0' && pid !== String(process.pid) && !pidsToKill.has(pid)){
                pidsToKill.add(pid);
              }
            }
          }
        }
        if(pidsToKill.size === 0){ resolve(false); return; }
        let pending = pidsToKill.size;
        for(const pid of pidsToKill){
          const k = spawn('taskkill', ['/PID', pid, '/F', '/T'], { windowsHide: true, stdio: 'ignore' });
          k.on('close', () => {
            killed++;
            if(killed >= pidsToKill.size){ resolve(true); }
          });
          k.on('error', () => {
            killed++;
            if(killed >= pidsToKill.size){ resolve(true); }
          });
        }
      });
      child.on('error', () => resolve(false));
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
    const names = ["Arch-icon.png", "Arch.png", "Arch.ico"];
    const dirs = [];
    try { dirs.push(resolveAppRoot()); } catch(e){}
    if(process.execPath){ try { dirs.push(path.dirname(process.execPath)); } catch(e){} }
    if(process.resourcesPath){ try { dirs.push(process.resourcesPath); dirs.push(path.dirname(process.resourcesPath)); } catch(e){} }
    try { dirs.push(__dirname); } catch(e){}
    const seen = new Set();
    for(const d of dirs){
      if(!d || seen.has(d)) continue;
      seen.add(d);
      for(const n of names){
        try {
          const p = path.join(d, n);
          if(fs.existsSync(p)){
            const img = nativeImage.createFromPath(p);
            if(img && !img.isEmpty()) return img;
          }
        } catch(e){}
      }
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

function startBackend(win){
  try {
    const root = resolveAppRoot();
    const script = path.join(root, "api_server.py");
    const tries = [
      ["python",  ["-u", script]],
      ["pythonw", ["-u", script]],
      ["py",      ["-3", "-u", script]],
    ];
    let idx = 0;

    const escalate = () => {
      if(idx >= tries.length) idx = 0;
      const [cmd, args] = tries[idx++];
      backendProc = trySpawn(cmd, args, root);
    };

     (async () => {
        const pingResult = await pingBackend();
        if(pingResult === true) return; // already running with our token
        if(pingResult === 'unauthorized'){
          // Stale backend with a different token — kill it and restart
          await killProcessOnPort(API_PORT);
          await new Promise(r => setTimeout(r, 2000));
        }
        // Start backend FIRST (so UI becomes responsive quickly), then run ensureRuntimes in parallel
        if(runtimePython){ tries.unshift([runtimePython[0], [...runtimePython[1], "-u", script]]); idx = 0; }
        escalate();  // Start backend immediately
        // Silent first-run setup: fetch Python / pip packages / VC++ if the host lacks them
        // Run in background — backend already starting
        ensureRuntimes(win).then(() => {
          // Re-check if backend came up after runtime installation
          for(let i = 0; i < 50; i++){
            setTimeout(() => {}, 200);
          }
        });
        for(let i = 0; i < 250; i++){  // 50s max wait
          await new Promise(r => setTimeout(r, 200));
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
  // Expose win to the module scope for startBackend bootstrap status
  global._mainWindow = win;
  if(icon) {
    try { win.setIcon(icon); } catch(e){}
  }
  hardenWebContents(win.webContents, win);
   // Block any non-local network traffic from the renderer, but allow localhost API calls
   // and MathJax CDN for math rendering
   session.defaultSession.webRequest.onBeforeRequest({ urls: ["http://*/*", "https://*/*"] }, (details, cb) => {
     const u = new URL(details.url);
     const isLocalAPI = u.hostname === API_HOST && u.port === String(API_PORT);
     if(isLocalAPI){ cb({ cancel: false }); return; }
     // Allow localhost on any port (for dev mode)
     const isLocalhost = u.hostname === "localhost" || u.hostname === "127.0.0.1" || u.hostname === "::1";
     if(isLocalhost){ cb({ cancel: false }); return; }
     // Allow MathJax CDN for math rendering
     if(u.hostname === "cdn.jsdelivr.net"){ cb({ cancel: false }); return; }
     cb({ cancel: true });
   });
      const appRoot = path.dirname(process.execPath);
      let forceIntro = false;
      try {
        const seenFile = path.join(app.getPath('userData'), 'arch.intro.seen');
        const seenFileApp = path.join(resolveAppRoot(), 'arch.intro.seen');
        forceIntro = fs.existsSync(path.join(appRoot, "ALWAYS_SHOW_INTRO")) || fs.existsSync(path.join(resolveAppRoot(), "ALWAYS_SHOW_INTRO"));
        if (!forceIntro && !fs.existsSync(seenFile) && !fs.existsSync(seenFileApp)) {
          // First-time launch: always show intro notification
          forceIntro = true;
        }
      } catch(e){}
      // Resolve index.html path — try ASAR first, then disk
      const indexPath = path.join(resolveAppRoot(), "index.html");
      const asarPath = path.join(process.resourcesPath || appRoot, "app.asar", "index.html");
      const indexFile = fs.existsSync(indexPath) ? indexPath : fs.existsSync(asarPath) ? asarPath : indexPath;
      win.loadFile(indexFile, { query: { token: TOKEN, appRoot, intro: forceIntro ? "1" : "0" } }).catch((err) => {
        console.error("Failed to load index.html:", err.message);
      });
    win.show();
    win.on("ready-to-show", () => {
      win.show();
      win.focus();
    });
    win.on("unresponsive", () => {
      try { win.focus(); } catch(e){}
    });
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
   createWindow();
   startBackend(global._mainWindow);

  // IPC: Open URLs in default browser (only URLs, no local apps)
  ipcMain.handle('open-url', async (event, url) => {
    try {
      if(url && (url.startsWith('http://') || url.startsWith('https://'))){
        await shell.openExternal(url);
        return { ok: true };
      }
      return { ok: false, error: 'Not a URL' };
    } catch(e){
      return { ok: false, error: e.message };
    }
  });

  // IPC: Mark intro as seen (creates marker file in userData for first-run tracking)
  ipcMain.handle('intro-seen', async () => {
    try {
      const seenFile = path.join(app.getPath('userData'), 'arch.intro.seen');
      fs.writeFileSync(seenFile, '1');
      return { ok: true };
    } catch(e){
      return { ok: false };
    }
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", () => {
  killProcessOnPort(API_PORT);
  if(backendProc){
    try { backendProc.kill(); } catch(e){}
    backendProc = null;
  }
  // Kill the portable Ollama server (port 11435) AND any child processes
  killProcessOnPort(11435);
  // Also kill system-level Ollama (port 11434) and all ollama processes
  killProcessOnPort(11434);
  // Kill any lingering ollama.exe processes
  try {
    const { execSync } = require("child_process");
    execSync("taskkill /F /IM ollama.exe /T 2>nul || true", { windowsHide: true, timeout: 5000 });
  } catch(e){}
  // Force-kill any orphaned llama-server or arch processes
  try {
    const { execSync } = require("child_process");
    execSync("taskkill /F /IM llama-server.exe /T 2>nul || true", { windowsHide: true, timeout: 5000 });
  } catch(e){}
  // Signal the backend API server to stop Ollama cleanly
  try {
    const http = require("http");
    const req = http.request({ hostname: "127.0.0.1", port: API_PORT, path: "/api/shutdown", method: "POST", timeout: 2000 }, () => {});
    req.on("error", () => {});
    req.end();
  } catch(e){}
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
