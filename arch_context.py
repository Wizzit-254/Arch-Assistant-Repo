"""Constants, config loader, and runtime context shared by the Arch backend."""
import os
import sys
import json

def _resolve_app_dir():
    """Resolve the application directory across frozen and dev environments.

    When frozen by PyInstaller, sys._MEIPASS is the temp extraction dir and
    sys.executable is the bundled binary — neither points at the real app
    root where Config.json, ollama/, and the .Modelfile files live.

    Priority:
      1. ARCH_APP_DIR env var (set by main.js via process.env)
      2. PORTABLE_EXECUTABLE_DIR env var (Electron sets this automatically)
      3. parent of sys.executable (frozen PyInstaller binary in dist/)
      4. sys._MEIPASS (PyInstaller temp dir — usually wrong for our layout)
      5. __file__ parent (dev mode)
    """
    candidates = []
    env_app = os.environ.get("ARCH_APP_DIR")
    if env_app:
        candidates.append(env_app)
    ped = os.environ.get("PORTABLE_EXECUTABLE_DIR")
    if ped:
        candidates.append(ped)
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.basename(exe_dir) == "dist":
            candidates.append(os.path.dirname(exe_dir))
        else:
            candidates.append(exe_dir)
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(meipass)
    candidates.append(os.path.dirname(os.path.abspath(__file__)))
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = _resolve_app_dir()
OLLAMA_DIR = os.path.join(APP_DIR, "ollama")
OLLAMA_EXE = os.path.join(OLLAMA_DIR, "ollama.exe")
OLLAMA_MODELS = os.path.join(OLLAMA_DIR, "models")
OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11435

# Electron-facing API server (CDP-style)
API_HOST = "127.0.0.1"
API_PORT = 9224

CONFIG_PATH = os.path.join(APP_DIR, "Config.json")
CHATS_FILE = os.path.join(os.path.dirname(APP_DIR), "arch-assistant", "chats.json")
# Fallback: store chats.json alongside Config.json if the roaming dir doesn't exist
if not os.path.isdir(os.path.dirname(CHATS_FILE)):
    os.makedirs(os.path.dirname(CHATS_FILE), exist_ok=True)
    CHATS_FILE = os.path.join(APP_DIR, "chats.json")


def load_config():
    defaults = {
        "api_port": API_PORT,
        "ollama_port": OLLAMA_PORT,
        "default_model": "luna-5.3",
        "profile": {"name": "User", "nickname": "User", "language": "en", "theme": "dark", "voice": "Sabrina"},
    }
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        defaults.update(cfg)
        return defaults
    except Exception:
        return defaults


CONFIG = load_config()

FISH_API_KEY = CONFIG.get("fish_api_key", "")
FISH_VOICES = CONFIG.get("fish_voices", {})


class ArchContext:
    """Mutable runtime context (profile + active model)."""
    def __init__(self):
        self.model = CONFIG.get("default_model")
        prof = CONFIG.get("profile", {})
        self.name = prof.get("name", "User")
        self.nickname = prof.get("nickname", "User")
        self.language = prof.get("language", "en")
        self.theme = prof.get("theme", "dark")
        self.voice = prof.get("voice", "Ember")

    def to_dict(self):
        return {
            "model": self.model,
            "name": self.name,
            "nickname": self.nickname,
            "language": self.language,
            "theme": self.theme,
            "voice": self.voice,
        }


CTX = ArchContext()
