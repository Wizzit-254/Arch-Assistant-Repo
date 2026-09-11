import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.error
from arch_context import APP_DIR

PORTABLE_PORT = 11435
SYSTEM_PORT = 11434
PORTABLE_HOST = f"http://127.0.0.1:{PORTABLE_PORT}"
SYSTEM_HOST = f"http://localhost:{SYSTEM_PORT}"

BASE_MODELS = {
    "luna-5.3": ("qwen2.5-coder:3b-instruct-q4_K_S", "Luna.Modelfile"),
    # Fable is Arch's math + full-stack coding specialist — uses the strongest
    # 7B code+math model that still runs under 4 GB RAM (~3.25 GB on disk, q3_K_S).
    "wun-3.8": ("qwen2.5-coder:7b-instruct-q3_K_S", "Wun.Modelfile"),
    "mushy-4.6": ("qwen2.5-coder:3b-instruct-q4_K_S", "Mushy.Modelfile"),
}

PORTABLE_DIR = os.path.join(APP_DIR, 'ollama')
# Binary name is platform-specific (wizard installs the right one per OS).
OLLAMA_EXE = os.path.join(PORTABLE_DIR, "ollama.exe" if os.name == "nt" else "ollama")
PORTABLE_MODELS = os.path.join(PORTABLE_DIR, 'models')


def is_portable():
    return bool(OLLAMA_EXE) and os.path.isfile(OLLAMA_EXE)


def _env_for_portable():
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = PORTABLE_MODELS
    env["OLLAMA_HOST"] = f"127.0.0.1:{PORTABLE_PORT}"
    # Keep models loaded in RAM for up to 4 hours between requests (avoids slow reloads)
    env["OLLAMA_KEEP_ALIVE"] = "4h"
    # Only ONE model resident at a time: with ~3 GB free, two models
    # (e.g. 1 GB Luna + 3.3 GB Fable) thrash the pagefile and decode
    # collapses (~0.2 tok/s measured). Single residency decodes ~18x faster;
    # switching models costs one reload, which the thinking orb covers.
    env["OLLAMA_MAX_LOADED_MODELS"] = "1"
    # Disable GPU features to save memory on low-end PCs
    env["OLLAMA_GPU_OVERHEAD"] = "0"
    # Flash attention: faster prompt processing + smaller KV cache on CPU
    env["OLLAMA_FLASH_ATTENTION"] = "1"
    return env


def _http_get(host, path, timeout=2):
    try:
        req = urllib.request.Request(
            host.rstrip('/') + path,
            method="GET",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode() or '{}')
    except Exception:
        pass
    return None


def fetch_models(host=None):
    host = host or get_active_host()
    data = _http_get(host, "/api/tags", timeout=2)
    if not data:
        return []
    return [m.get("name", "") for m in data.get("models", [])]


def _is_reachable(host):
    return _http_get(host, "/api/tags", timeout=1) is not None


def _start_portable_serve():
    if _is_reachable(PORTABLE_HOST):
        return True
    if not is_portable():
        return False
    try:
        os.makedirs(PORTABLE_MODELS, exist_ok=True)
        if os.name == "nt":
            flags = 0x08000000 | subprocess.DETACHED_PROCESS
            proc_kwargs = dict(creationflags=flags)
        else:
            # macOS/Linux: detach into its own session, silence output
            proc_kwargs = dict(start_new_session=True)
        subprocess.Popen(
            [OLLAMA_EXE, "serve"],
            env=_env_for_portable(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **proc_kwargs,
        )
    except Exception:
        return False
    for _ in range(20):
        time.sleep(0.5)
        if _is_reachable(PORTABLE_HOST):
            return True
    return _is_reachable(PORTABLE_HOST)


def _pids_listening_on(port):
    """PIDs with a TCP LISTEN socket on 127.0.0.1:port.

    Windows: parses `netstat -ano`. macOS/Linux: uses `lsof -ti`.
    """
    pids = set()
    try:
        if os.name != "nt":
            out = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"],
                capture_output=True, timeout=15,
            )
            for token in (out.stdout or b"").decode("utf-8", "replace").split():
                if token.strip().isdigit():
                    pids.add(token.strip())
            return pids
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, timeout=15,
            creationflags=0x08000000 if os.name == 'nt' else 0,
        )
        for line in (out.stdout or b"").decode("utf-8", "replace").splitlines():
            if "LISTENING" not in line:
                continue
            parts = line.split()
            if len(parts) >= 5 and parts[0].upper() == "TCP" \
                    and parts[1].rsplit(":", 1)[-1] == str(port) \
                    and parts[4].isdigit() and parts[4] != "0":
                pids.add(parts[4])
    except Exception:
        pass
    return pids


def stop_portable():
    """Stop the bundled portable Ollama server and free its RAM. Best-effort.

    Only kills the process tree listening on PORTABLE_PORT, so a system-wide
    Ollama on 11434 is never touched. Returns True when the port is free.
    """
    try:
        for pid in _pids_listening_on(PORTABLE_PORT):
            if pid == str(os.getpid()):
                continue
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid, "/T"],
                        capture_output=True, timeout=30,
                        creationflags=0x08000000 if os.name == 'nt' else 0,
                    )
                else:
                    subprocess.run(["kill", "-9", str(pid)], capture_output=True, timeout=30)
            except Exception:
                pass
        for _ in range(10):
            if not _is_reachable(PORTABLE_HOST) and not _pids_listening_on(PORTABLE_PORT):
                _wlog("portable ollama stopped")
                return True
            time.sleep(0.5)
    except Exception as e:
        _wlog(f"stop err={str(e)[:120]}")
    return not _is_reachable(PORTABLE_HOST)


def start_system_ollama():
    try:
        if os.name == "nt":
            cands = [
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
                os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe"),
            ]
        else:
            # macOS: Homebrew, /usr/local, or the official Ollama.app
            cands = [
                "/opt/homebrew/bin/ollama",
                "/usr/local/bin/ollama",
                "/Applications/Ollama.app/Contents/Resources/ollama",
            ]
        path = next((p for p in cands if p and os.path.exists(p)), None)
        if path:
            if os.name == "nt":
                subprocess.Popen([path, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=0x08000000)
            else:
                subprocess.Popen([path, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            return True
    except Exception:
        pass
    return False


def ensure_ollama():
    """Starts the best available Ollama runtime and returns its host URL.

    Bundled portable Ollama (this folder -> ollama\\ollama.exe), which keeps all
    models inside the folder so it works on any PC, is preferred. Falls back to a
    system-wide Ollama install on localhost:11434.

    This is the lazy-restart entry point: if the idle watchdog already stopped
    Ollama, this call restarts it on demand.
    """
    touch_activity()
    if is_portable():
        if _start_portable_serve():
            return PORTABLE_HOST
    if _is_reachable(SYSTEM_HOST):
        return SYSTEM_HOST
    start_system_ollama()
    for _ in range(6):
        time.sleep(0.5)
        if _is_reachable(SYSTEM_HOST):
            return SYSTEM_HOST
    return PORTABLE_HOST if is_portable() else SYSTEM_HOST


def get_active_host():
    """Cheap host lookup used by local_ai / GUI when the server is expected up."""
    if is_portable():
        if _is_reachable(PORTABLE_HOST):
            return PORTABLE_HOST
        if _is_reachable(SYSTEM_HOST):
            return SYSTEM_HOST
        return PORTABLE_HOST
    return SYSTEM_HOST


# --- Idle-stop watchdog: stop Ollama after a configurable idle period ---
# Saves RAM when the user walks away for a long time. Ollama is lazily
# restarted on the next request via ensure_ollama(). Kept LONG (60 min) so
# the model stays hot in RAM during a normal session — killing it is what
# made every other question pay a full multi-GB model reload.
IDLE_TIMEOUT_SECONDS = 3600  # 60 minutes idle -> stop Ollama
_tts_last_activity = 0.0
_idle_watchdog_running = False


def touch_activity():
    """Update the last-activity timestamp so the idle watchdog knows the
    user is still interacting with the model."""
    global _tts_last_activity
    _tts_last_activity = time.time()


def _idle_watchdog():
    """Background thread: stop Ollama after IDLE_TIMEOUT_SECONDS of inactivity.

    Calls ensure_ollama() again (which restarts the server) only when the
    next chat request arrives — this is the lazy-restart side of the cycle.
    """
    global _idle_watchdog_running
    _wlog("idle-watchdog started")
    while _idle_watchdog_running:
        time.sleep(30)
        if not _idle_watchdog_running:
            break
        try:
            elapsed = time.time() - _tts_last_activity
            if elapsed > IDLE_TIMEOUT_SECONDS and _is_reachable(PORTABLE_HOST):
                _wlog(f"idle {elapsed:.0f}s > {IDLE_TIMEOUT_SECONDS}s — stopping ollama")
                stop_portable()
            elif elapsed > IDLE_TIMEOUT_SECONDS and _is_reachable(SYSTEM_HOST):
                _wlog(f"idle {elapsed:.0f}s — stopping system ollama")
                _stop_system_ollama()
        except Exception:
            pass
    _wlog("idle-watchdog exited")


def start_idle_watchdog():
    """Start the idle-stop watchdog thread (idempotent)."""
    global _idle_watchdog_running
    if _idle_watchdog_running:
        return
    _idle_watchdog_running = True
    import threading
    t = threading.Thread(target=_idle_watchdog, daemon=True)
    t.start()


def stop_idle_watchdog():
    """Signal the idle-stop watchdog to exit."""
    global _idle_watchdog_running
    _idle_watchdog_running = False


def _stop_system_ollama():
    """Kill the system-level Ollama server (port 11434)."""
    try:
        import os as _os
        if _os.name != "nt":
            out = subprocess.run(["pkill", "-f", "ollama"], capture_output=True, timeout=10)
        else:
            for pid in _pids_listening_on(SYSTEM_PORT):
                if pid == str(_os.getpid()):
                    continue
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid), "/T"],
                    capture_output=True, timeout=10,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
    except Exception:
        pass


def _wlog(msg):
    try:
        with open(os.path.join(APP_DIR, "warmup.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S") + " " + str(msg)[:300] + "\n")
    except Exception:
        pass


def warmup_model(model="luna-5.3", timeout=240):
    """Pre-load `model` into RAM so the first real question answers fast.

    Runs in a background thread at startup: waits for Ollama to be reachable,
    then issues a tiny 1-token generate that forces the weights to load while
    the user is still on the home screen. Best-effort — never raises.
    """
    try:
        _wlog(f"warmup start model={model}")
        time.sleep(15)  # let ensure_ollama/ensure_custom_models settle first
        for _attempt in range(8):
            host = None
            for _ in range(120):
                try:
                    host = get_active_host()
                    if _is_reachable(host):
                        break
                except Exception:
                    pass
                host = None
                time.sleep(0.5)
            if not host:
                _wlog(f"attempt {_attempt}: ollama not reachable")
                return False
            try:
                body = json.dumps({
                    "model": model,
                    "prompt": "hi",
                    "stream": False,
                    "keep_alive": "4h",
                    "options": {"num_predict": 1, "num_ctx": 1536, "num_batch": 512},
                }).encode("utf-8")
                req = urllib.request.Request(
                    host.rstrip("/") + "/api/generate", data=body, method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        _wlog(f"attempt {_attempt}: warm OK host={host}")
                        return True
                    _wlog(f"attempt {_attempt}: status={resp.status}")
            except Exception as e:
                _wlog(f"attempt {_attempt}: err={str(e)[:150]}")
            time.sleep(45)
        return False
    except Exception:
        return False


def _cli(args, env=None, timeout=600):
    if not is_portable():
        cmd = ["ollama"] + args
        use_env = None
    else:
        cmd = [OLLAMA_EXE] + args
        use_env = env or _env_for_portable()
    try:
        return subprocess.run(
            cmd, env=use_env, capture_output=True, timeout=timeout,
            creationflags=0x08000000 if os.name == 'nt' else 0,
        )
    except Exception:
        return None


def _modelfile_path(mfile):
    """Find a .Modelfile by name, searching multiple candidate locations.

    In a frozen build the Modelfiles are bundled alongside the executable,
    but _MEIPASS may also contain them if PyInstaller was configured to
    include them via --add-data.
    """
    cands = [
        os.path.join(APP_DIR, mfile),
        os.path.join(getattr(sys, '_MEIPASS', ''), mfile),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), mfile),
    ]
    for cand in cands:
        if cand and os.path.isfile(cand):
            return cand
    return None


def _model_has_blobs(model_name):
    """Check if a model's manifest references blobs that actually exist on disk."""
    manifest_path = os.path.join(
        PORTABLE_MODELS, "manifests", "registry.ollama.ai", "library", model_name, "latest"
    )
    if not os.path.isfile(manifest_path):
        return False
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        for layer in manifest.get("layers", []):
            digest = layer.get("digest", "")
            if not digest:
                continue
            blob_name = digest.replace(":", "-", 1)
            blob_path = os.path.join(PORTABLE_MODELS, "blobs", blob_name)
            if not os.path.isfile(blob_path):
                return False
        return True
    except Exception:
        return False


def _is_offline():
    """Quick check: can we reach the internet at all?

    Any HTTP response (including 4xx like 404) means we HAVE internet —
    only connection errors, timeouts, and DNS failures mean offline.
    This lets us fall through to the "cannot pull" fallback gracefully.
    """
    import urllib.error as _uerr
    try:
        req = urllib.request.Request(
            "https://registry.ollama.ai/v2/", method="HEAD",
            headers={"User-Agent": "arch-assistant/1.0"},
        )
        with urllib.request.urlopen(req, timeout=1) as resp:
            return False
    except _uerr.HTTPError:
        # Got an HTTP response (4xx/5xx) → we have internet
        return False
    except (urllib.error.URLError, OSError, ConnectionError):
        return True
    except Exception:
        return True


def ensure_custom_models(host=None, existing=None):
    """Pulls the (quantized) base model and creates luna-5.3, wun-3.8,
    and mushy-4.6 on the runtime at `host`. All three share one base blob
    so the models stay tiny. Returns the list of models that are now
    available.

    Enforces a hard 12 GB storage cap for the portable runtime."""
    if not is_portable():
        return []
    current, limit, within = check_storage_cap()
    if not within:
        return []
    host = host or get_active_host()
    if existing is None:
        existing = fetch_models(host)
    created = []
    # Normalize existing model names (strip :latest suffix for comparison)
    existing_norm = set(m.split(":")[0] for m in existing)
    # Only check offline status if at least one model is missing (avoids network
    # call on every startup when models are already present)
    all_present = all(name in existing_norm and _model_has_blobs(name) for name, (base, mfile) in BASE_MODELS.items())
    offline = _is_offline() if not all_present else False
    for name, (base, mfile) in BASE_MODELS.items():
        if name in existing_norm and _model_has_blobs(name):
            created.append(name)
            continue
        mpath = _modelfile_path(mfile)
        if not mpath:
            print(f"[ollama] Modelfile not found for {name}, skipping", flush=True)
            continue
        if name in existing_norm and not _model_has_blobs(name):
            print(f"[ollama] {name} manifest exists but blobs missing, will attempt recreate", flush=True)
        if base is not None and not any(base in m for m in fetch_models(host)):
            if offline:
                print(f"[ollama] Offline — cannot pull base model {base} for {name}", flush=True)
                continue
            cap_now = check_storage_cap()
            if not cap_now[2]:
                break
            r = _cli(["pull", base])
            if not r or r.returncode != 0:
                print(f"[ollama] Failed to pull base model {base}", flush=True)
                continue
        cap_now = check_storage_cap()
        if not cap_now[2]:
            break
        r = _cli(["create", name, "-f", mpath])
        if r and r.returncode == 0:
            created.append(name)
        else:
            stderr_out = r.stderr.decode("utf-8", "replace") if r and r.stderr else ""
            print(f"[ollama] Failed to create {name}: {stderr_out[:200]}", flush=True)
    return created


def modelfile_paths():
    return {name: _modelfile_path(mfile) for name, (_, mfile) in BASE_MODELS.items()}


def portable_size_report():
    try:
        total = 0
        for root, _dirs, files in os.walk(PORTABLE_DIR):
            for f in files:
                total += os.path.getsize(os.path.join(root, f))
        return total
    except Exception:
        return 0


STORAGE_LIMIT_BYTES = 12 * 1024 * 1024 * 1024

def check_storage_cap():
    """Return (current_bytes, limit_bytes, within_cap)."""
    current = portable_size_report()
    return current, STORAGE_LIMIT_BYTES, current <= STORAGE_LIMIT_BYTES
