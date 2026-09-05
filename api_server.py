"""Arch Api Server (CDP-style local bridge on 127.0.0.1:9224).

Exposes the routes index.html expects:
  GET  /api/config            -> app config + active model/profile
  GET  /api/models            -> available models (luna-5.3, mushy-4.6, wun-3.8)
  POST /api/model             -> switch active model   {model:"..."}
  POST /api/chat              -> SSE text/event-stream from the ollama backend   {model?, messages:[], temperature?}
  POST /api/edit              -> SSE edit stream       {file, instruction, model?}
  POST /api/agent             -> start an agent task   {kind, task} -> returns a session id
  GET  /api/agent/:id         -> SSE agent progress (placeholder: routes to chat)
  POST /api/theme             -> {theme:"dark"|"light"}  (persisted to Config.json)
  POST /api/voice             -> {voice:"Ember"}  (persisted to Config.json)

Uses only the Python standard library (http.server) so it runs from the
bundled Arch runtime without extra packages.
"""
import os
import json
import threading
import time
import uuid
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from arch_context import (
    APP_DIR, API_HOST, API_PORT, CTX, OLLAMA_HOST, OLLAMA_PORT, OLLAMA_DIR,
    CONFIG_PATH, CHATS_FILE, FISH_VOICES, load_config,
)
import ollama_runtime
import local_ai

try:
    from socketserver import ThreadingMixIn
except Exception:
    pass

# Active agent sessions (kind -> {id, kind, task, messages, running})
AGENTS = {}

# ---- security ----
API_TOKEN = os.environ.get("ARCH_API_TOKEN", "")
MAX_BODY = 2 * 1024 * 1024  # 2 MB per request
MAX_MESSAGES = 40
MAX_MSG_LEN = 12000
MAX_NICK = 32
ALLOWED_LANGS = {"en", "sw", "ha", "yo", "zu", "ig", "am", "fr"}
RATE_WINDOW = 10.0
RATE_MAX = 40
_rate = {}  # ip -> deque of timestamps


def _load_chats():
    """Load chat history from the persistent chats file."""
    try:
        with open(CHATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "chats" in data:
                return data["chats"]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


def _save_chats(chats):
    """Persist chat history to the chats file."""
    try:
        os.makedirs(os.path.dirname(CHATS_FILE), exist_ok=True)
        with open(CHATS_FILE, "w", encoding="utf-8") as f:
            json.dump(chats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save chats error:", e, flush=True)


def _rate_ok(ip):
    import time
    from collections import deque
    now = time.time()
    dq = _rate.setdefault(ip, deque())
    while dq and now - dq[0] > RATE_WINDOW:
        dq.popleft()
    if len(dq) >= RATE_MAX:
        return False
    dq.append(now)
    return True


def _authorized(headers):
    if not API_TOKEN:
        return True
    return headers.get("Authorization") == "Bearer " + API_TOKEN


def _origin_ok(handler):
    """Only allow the Electron file:// renderer (Origin: null) and same-origin."""
    origin = handler.headers.get("Origin", "")
    if not origin:
        return True
    return origin in ("null", "file://") or origin.startswith("file://")


def sse_headers():
    return {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-store",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }


def emit_event(payload, event="message", id=None):
    out = ""
    ev = ""
    if id is not None:
        ev += f"id: {id}\n"
    if event:
        ev += f"event: {event}\n"
    lines = payload if isinstance(payload, (list, tuple)) else [payload]
    for ln in lines:
        data = ln if isinstance(ln, str) else json.dumps(ln, ensure_ascii=False)
        for line in data.split("\n"):
            ev += "data: " + line + "\n"
    return ev + "\n"


def read_body(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if not length:
        return {}
    if length > MAX_BODY:
        handler.send_error(413, "Payload Too Large")
        return None
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return {"_raw": raw.decode("utf-8", "replace")}


def find_model_by_name(name):
    """Resolve a persona name to the ollama model string."""
    return local_ai.MODEL_OVERRIDES.get(name, name)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Arch"
    sys_version = ""

    def log_message(self, *a):
        return  # silent

    def _gate(self):
        """Return True if the request may proceed (auth + origin + rate)."""
        if not _origin_ok(self):
            self._send(403, {"error": "origin not allowed"})
            return False
        if not _authorized(self.headers):
            self._send(401, {"error": "unauthorized"})
            return False
        if not _rate_ok(self.client_address[0]):
            self._send(429, {"error": "too many requests"})
            return False
        return True

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send(self, code, obj, ctype="application/json"):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_plain(self, code, text):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_sse_start(self):
        self.send_response(200)
        for k, v in sse_headers().items():
            self.send_header(k, v)
        self.send_header("Connection", "close")
        self._cors()
        self.end_headers()
        self.wfile.write(b": ready\n")
        self.wfile.flush()

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if not self._gate():
            return
        p = urlparse(self.path).path
        if p == "/api/config":
            self._send(200, {
                "model": CTX.model,
                "model_display": local_ai.display_model(CTX.model),
                "models": list(local_ai.MODEL_OVERRIDES.keys()),
                "models_display": local_ai.MODEL_DISPLAY,
                "profile": {"name": CTX.name, "nickname": CTX.nickname, "language": CTX.language,
                             "theme": CTX.theme, "voice": CTX.voice},
                "ollama": {"host": OLLAMA_HOST, "port": OLLAMA_PORT},
                "api_port": API_PORT,
                "fish_voices": FISH_VOICES,
                "version": "1.0.0",
            })
            return
        if p == "/api/models":
            available = local_ai.list_models()
            internal = list({k for k in local_ai.MODEL_OVERRIDES.keys() if k in local_ai.MODEL_DISPLAY})
            self._send(200, {
                "models": [{"name": v, "id": k} for k, v in local_ai.MODEL_DISPLAY.items()],
                "active": CTX.model,
                "available": available,
            })
            return
        if p.startswith("/api/agent/"):
            # SSE stream for a running agent task (placeholder: reuse chat)
            aid = p.rsplit("/", 1)[-1]
            agent = AGENTS.get(aid)
            if not agent:
                self._send(404, {"error": "agent not found"})
                return
            self._send_sse_start()
            msgs = agent["messages"]
            try:
                for piece in local_ai.chat_stream(msgs, model=agent.get("model")):
                    self.wfile.write(emit_event({"model": agent["model"], **piece}).encode("utf-8"))
                    self.wfile.flush()
                self.wfile.write(emit_event({"done": True, "agent": aid}, event="done").encode("utf-8"))
                self.wfile.flush()
            except Exception as e:
                self.wfile.write(emit_event({"error": str(e)}, event="error").encode("utf-8"))
            return
        if p == "/api/chats":
            self._send(200, {"chats": _load_chats()})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._gate():
            return
        p = urlparse(self.path).path
        body = read_body(self)
        if body is None:
            return
        if p == "/api/model":
            wanted = body.get("model")
            if wanted in local_ai.MODEL_OVERRIDES or find_model_by_name(wanted):
                CTX.model = local_ai.MODEL_OVERRIDES.get(wanted, wanted)
                self._update_config("default_model", CTX.model)
                self._send(200, {"model": CTX.model})
            else:
                self._send(400, {"error": "unknown model"})
            return
        if p == "/api/theme":
            theme = body.get("theme", CTX.theme)
            CTX.theme = theme
            self._update_config_profile("theme", theme)
            self._send(200, {"theme": theme})
            return
        if p == "/api/voice":
            voice = body.get("voice", CTX.voice)
            CTX.voice = voice
            self._update_config_profile("voice", voice)
            self._send(200, {"voice": voice})
            return
        if p == "/api/profile":
            changed = False
            nick = str(body.get("nickname", "")).strip()[:MAX_NICK]
            lang = str(body.get("language", "")).strip().lower()[:5]
            if body.get("nickname") is not None and nick:
                CTX.nickname = nick; changed = True
            if lang in ALLOWED_LANGS:
                CTX.language = lang; changed = True
            if body.get("name") is not None:
                CTX.name = str(body["name"]).strip()[:MAX_NICK] or CTX.name; changed = True
            if changed:
                self._update_config_profile_multi({
                    "name": CTX.name,
                    "nickname": CTX.nickname,
                    "language": CTX.language,
                })
            self._send(200, {"name": CTX.name, "nickname": CTX.nickname, "language": CTX.language})
            return
        if p == "/api/chat":
            self._handle_chat(body)
            return
        if p == "/api/search":
            self._handle_search(body)
            return
        if p == "/api/stt":
            self._handle_stt(body)
            return
        if p == "/api/tts":
            self._handle_tts(body)
            return
        if p == "/api/edit":
            self._handle_edit(body)
            return
        if p == "/api/agent":
            self._handle_agent(body)
            return
        if p == "/api/chats":
            _save_chats(body.get("chats", []))
            self._send(200, {"ok": True})
            return
        if p == "/api/codebase/scan":
            root = body.get("root") or None
            result = local_ai.scan_codebase(root)
            self._send(200, result)
            return
        if p == "/api/codebase/search":
            query = body.get("query", "")
            root = body.get("root") or None
            results = local_ai.search_codebase(query, root)
            self._send(200, {"results": results})
            return
        if p == "/api/codebase/read":
            filepath = body.get("path", "")
            content = local_ai.read_file_content(filepath)
            self._send(200, {"path": filepath, "content": content})
            return
        if p == "/api/codebase/context":
            root = body.get("root") or None
            msgs = body.get("messages", [])
            msgs = local_ai.inject_codebase_context(msgs)
            self._send(200, {"messages": msgs})
            return
        if p == "/api/open":
            target = body.get("target", "")
            try:
                import subprocess as _sp
                _sp.Popen(["cmd", "/c", "start", "", target],
                          creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0))
                self._send(200, {"ok": True, "target": target})
            except Exception as e:
                self._send(500, {"error": str(e)})
            return
        self._send(404, {"error": "not found"})

    def _update_config(self, key, value):
        try:
            cfg = load_config()
            cfg[key] = value
            with open(os.path.join(APP_DIR, "Config.json"), "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def _update_config_profile(self, key, value):
        try:
            cfg = load_config()
            prof = dict(cfg.get("profile", {}))
            prof[key] = value
            cfg["profile"] = prof
            with open(os.path.join(APP_DIR, "Config.json"), "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            if key == "theme":
                CTX.theme = value
            elif key == "voice":
                CTX.voice = value
        except Exception:
            pass

    def _update_config_profile_multi(self, mapping):
        try:
            cfg = load_config()
            prof = dict(cfg.get("profile", {}))
            for k, v in mapping.items():
                prof[k] = v
                if k == "theme":
                    CTX.theme = v
                elif k == "voice":
                    CTX.voice = v
                elif k == "nickname":
                    CTX.nickname = v
                elif k == "language":
                    CTX.language = v
                elif k == "name":
                    CTX.name = v
            cfg["profile"] = prof
            with open(os.path.join(APP_DIR, "Config.json"), "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def _handle_chat(self, body):
        raw_msgs = body.get("messages", [])
        messages = []
        for m in raw_msgs[:MAX_MESSAGES]:
            if not isinstance(m, dict):
                continue
            role = m.get("role", "")
            content = str(m.get("content", ""))[:MAX_MSG_LEN]
            if role in ("user", "assistant", "system") and content:
                messages.append({"role": role, "content": content})
        if not messages:
            self._send(400, {"error": "no messages"})
            return
        model = body.get("model")
        temperature = body.get("temperature", 0.3)
        top_p = body.get("top_p", 0.9)
        top_k = body.get("top_k", 20)
        search = bool(body.get("search", False))
        inject_codebase = bool(body.get("codebase_context", False))
        if inject_codebase:
            messages = local_ai.inject_codebase_context(messages)
        self._send_sse_start()
        try:
            full_text = ""
            for piece in local_ai.chat_stream(
                messages, model=model, temperature=temperature,
                top_p=top_p, top_k=top_k, search=search,
            ):
                if isinstance(piece, dict):
                    content = piece.get("content", "")
                    full_text += content
                else:
                    full_text += str(piece)
                self.wfile.write(emit_event(piece).encode("utf-8"))
                self.wfile.flush()
            import re
            open_match = re.search(
                r"(?:open|launch|start)\s+(https?://[^\s]+|\b\w+\.exe\b|notepad|calc|explorer|chrome|firefox|edge|word|excel|powerpnt)\b",
                full_text, re.IGNORECASE
            )
            if open_match:
                target = open_match.group(0)
                # Extract the URL or app name after the verb
                for prefix in ("open ", "launch ", "start "):
                    if target.lower().startswith(prefix):
                        target = target[len(prefix):]
                        break
                target = target.strip().rstrip(".")
                self.wfile.write(emit_event({"action": "open", "target": target}, event="system_action").encode("utf-8"))
                self.wfile.flush()
                _sp.Popen(["cmd", "/c", "start", "", target],
                          stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
                          creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0))
            self.wfile.write(emit_event(None, event="done").encode("utf-8"))
            self.wfile.flush()
        except Exception as e:
            self.wfile.write(emit_event({"error": str(e)}, event="error").encode("utf-8"))

    def _handle_search(self, body):
        query = body.get("query", "")
        n = int(body.get("n", 5))
        results = local_ai.web_search(query, n=n) if query else []
        self._send(200, {"query": query, "count": len(results), "results": results})

    def _handle_stt(self, body):
        duration = min(max(int(body.get("duration", 8)), 1), 20)
        import subprocess
        ps = os.path.join(APP_DIR, "speech_stt.ps1")
        if not os.path.exists(ps):
            self._send(500, {"error": "speech_stt.ps1 missing", "text": ""})
            return
        try:
            proc = subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", ps, "-Duration", str(duration)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            text, _ = proc.communicate(timeout=duration + 15)
            out = text.decode("utf-8", "replace")
            parts = [ln[5:].strip() for ln in out.splitlines() if ln.startswith("TEXT:")]
            recognized = " ".join(parts).strip()
            self._send(200, {"text": recognized, "partial": False})
        except Exception as e:
            self._send(200, {"error": str(e), "text": ""})

    def _handle_tts(self, body):
        text = body.get("text", "")
        voice_id = body.get("voice_id") or body.get("voice") or ""
        # accept a display name from Config's fish_voices map too
        if voice_id in FISH_VOICES:
            voice_id = FISH_VOICES[voice_id]
        if not text.strip():
            self._send(400, {"error": "text required"})
            return
        if not voice_id:
            self._send(400, {"error": "voice_id required"})
            return
        audio = local_ai.fish_tts(text, voice_id)
        if not audio:
            self._send(502, {"error": "fish tts unavailable (check API key/credits)"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(audio)
        except Exception:
            pass

    def _handle_edit(self, body):
        file_text = body.get("file", "")
        instruction = body.get("instruction", "")
        model = body.get("model")
        self._send_sse_start()
        try:
            for piece in local_ai.edit_stream(file_text, instruction, model=model):
                self.wfile.write(emit_event(piece).encode("utf-8"))
                self.wfile.flush()
            self.wfile.write(emit_event(None, event="done").encode("utf-8"))
            self.wfile.flush()
        except Exception as e:
            self.wfile.write(emit_event({"error": str(e)}, event="error").encode("utf-8"))

    def _handle_agent(self, body):
        kind = body.get("kind", "Fix a bug")
        task = body.get("task", "")
        model = body.get("model") or CTX.model
        aid = "ag_" + uuid.uuid4().hex[:12]
        AGENTS[aid] = {
            "id": aid, "kind": kind, "task": task, "model": model,
            "running": False,
            "messages": [{"role": "user", "content": f"[{kind}] {task}"}],
        }
        self._send(200, {"id": aid, "kind": kind, "status": "queued"})

    def end_headers(self):
        super().end_headers()


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def ensure_ollama():
    """Make sure the portable ollama runtime is up on OLLAMA_PORT."""
    try:
        host = ollama_runtime.ensure_ollama()
        ollama_runtime.ensure_custom_models()
        return host
    except Exception as e:
        print("ollama init error:", e, flush=True)
        return None


def _ollama_health_loop():
    """Background thread: periodically check ollama liveness and restart if dead.

    This prevents the 'backend disconnecting' issue — if ollama crashes or
    gets killed (e.g. by OOM), the server will restart it automatically."""
    while True:
        time.sleep(15)
        try:
            host = ollama_runtime.get_active_host()
            if not ollama_runtime._is_reachable(host):
                print("[health] ollama unreachable, restarting...", flush=True)
                ollama_runtime.ensure_ollama()
        except Exception:
            pass


def main():
    print(f"Arch Api Server starting on http://{API_HOST}:{API_PORT}", flush=True)
    srv = Server((API_HOST, API_PORT), Handler)
    serve_thread = threading.Thread(target=srv.serve_forever, daemon=True)
    serve_thread.start()
    # Verify the port is actually listening before spawning the heavy init thread
    import socket as _sock
    for _ in range(50):
        try:
            with _sock.create_connection((API_HOST, API_PORT), timeout=0.5):
                break
        except OSError:
            pass
        time.sleep(0.1)
    threading.Thread(target=ensure_ollama, daemon=True).start()
    threading.Thread(target=_ollama_health_loop, daemon=True).start()
    try:
        serve_thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
        srv.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()

