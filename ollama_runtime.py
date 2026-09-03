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
    "wun-3.8": ("qwen2.5-coder:3b-instruct-q4_K_S", "Wun.Modelfile"),
    "mushy-4.6": ("qwen2.5-coder:3b-instruct-q4_K_S", "Mushy.Modelfile"),
}

PORTABLE_DIR = os.path.join(APP_DIR, 'ollama')
OLLAMA_EXE = os.path.join(PORTABLE_DIR, 'ollama.exe')
PORTABLE_MODELS = os.path.join(PORTABLE_DIR, 'models')


def is_portable():
    return bool(OLLAMA_EXE) and os.path.isfile(OLLAMA_EXE)


def _env_for_portable():
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = PORTABLE_MODELS
    env["OLLAMA_HOST"] = f"127.0.0.1:{PORTABLE_PORT}"
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
        flags = 0x08000000 | subprocess.DETACHED_PROCESS
        subprocess.Popen(
            [OLLAMA_EXE, "serve"],
            env=_env_for_portable(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception:
        return False
    for _ in range(20):
        time.sleep(0.5)
        if _is_reachable(PORTABLE_HOST):
            return True
    return _is_reachable(PORTABLE_HOST)


def start_system_ollama():
    try:
        path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
        if not os.path.exists(path):
            path = os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe")
        if os.path.exists(path):
            flags = 0x08000000
            subprocess.Popen([path, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            return True
    except Exception:
        pass
    return False


def ensure_ollama():
    """Starts the best available Ollama runtime and returns its host URL.

    Bundled portable Ollama (this folder -> ollama\\ollama.exe), which keeps all
    models inside the folder so it works on any PC, is preferred. Falls back to a
    system-wide Ollama install on localhost:11434.
    """
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
    """Quick check: can we reach the internet at all?"""
    try:
        req = urllib.request.Request(
            "https://registry.ollama.ai/v2/", method="HEAD",
            headers={"User-Agent": "arch-assistant/1.0"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status < 400
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
    offline = _is_offline()
    for name, (base, mfile) in BASE_MODELS.items():
        if name in existing and _model_has_blobs(name):
            created.append(name)
            continue
        mpath = _modelfile_path(mfile)
        if not mpath:
            print(f"[ollama] Modelfile not found for {name}, skipping", flush=True)
            continue
        if name in existing and not _model_has_blobs(name):
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
