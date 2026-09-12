"""
Local AI bridge: ollama HTTP client used by Api_server.

All heavy lifting talks to the portable ollama runtime on 127.0.0.1:11435.
Personality model names (luna-5.3, mushy-4.6, wun-3.8) map to display names
(Terra 5.3, Chen Instruct 3, Fable 5.1) and ollama model names (created via the .Modelfile files).
"""
import os
import re
import html
import math
import json as _json
import json
import hashlib
import tempfile
import urllib.request
import urllib.error
import urllib.parse
import time

from arch_context import OLLAMA_HOST, OLLAMA_PORT, CTX, FISH_API_KEY, APP_DIR, FISH_VOICES, FISH_CONFIGURED, TTS_RATE_LIMIT_SECONDS

OLLAMA_BASE = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"

# TTS rate-limit state: track last API call time to avoid burning credits
_tts_last_call_time = 0.0


def _rate_limit_tts(key, cache_dir):
    """Enforce a minimum interval between TTS API calls to limit credit usage.

    Uses a per-process global timestamp plus a small marker file so the
    limit persists across restarts. Cached results bypass this entirely.
    """
    global _tts_last_call_time
    marker = os.path.join(cache_dir, ".tts_last_call")
    try:
        if os.path.exists(marker):
            mtime = os.path.getmtime(marker)
            if mtime > _tts_last_call_time:
                _tts_last_call_time = mtime
    except Exception:
        pass
    elapsed = time.time() - _tts_last_call_time
    if elapsed < TTS_RATE_LIMIT_SECONDS:
        wait = TTS_RATE_LIMIT_SECONDS - elapsed
        print(f"TTS rate-limit: waiting {wait:.1f}s before API call", flush=True)
        time.sleep(wait)
    _tts_last_call_time = time.time()
    try:
        with open(marker, "w") as f:
            f.write(str(_tts_last_call_time))
    except Exception:
        pass

# Model name overrides for the backend. luna/mushy/wun are ollama "create"d
# names; display names shown in the UI are mapped here.
MODEL_OVERRIDES = {
    "luna-5.3": "luna-5.3",
    "Terra 5.3": "luna-5.3",
    "mushy-4.6": "mushy-4.6",
    "Chen Instruct 3": "mushy-4.6",
    "wun-3.8": "wun-3.8",
    "Fable 5.1": "wun-3.8",
}
MODEL_DISPLAY = {
    "luna-5.3": "Terra 5.3",
    "mushy-4.6": "Chen Instruct 3",
    "wun-3.8": "Fable 5.1",
}

# Languages offered in Settings. AI answers in the chosen language with
# native-level grammar and idiom; UI strings fall back to English where a
# full UI translation does not exist yet.
SUPPORTED_LANGUAGES = {
    "en": "English", "sw": "Kiswahili", "fr": "French",
    "zh": "Mandarin", "ja": "Japanese", "ar": "Arabic",
}
AFRICAN_LANGUAGE_NAMES = SUPPORTED_LANGUAGES
AFRICAN_LANGS = set(SUPPORTED_LANGUAGES.keys())


def _fit_history(messages, budget_chars):
    """Keep the newest turns that fit a char budget (roughly 4 chars/token).

    A leading system message (e.g. injected web-search context) is always
    kept; oldest conversation turns are dropped first. Guarantees the model
    always sees recent turns + the current question inside num_ctx.
    """
    msgs = [m for m in (messages or [])
            if isinstance(m, dict) and str(m.get("content", ""))]
    if not msgs:
        return msgs
    head = []
    if msgs[0].get("role") == "system":
        head = msgs[:1]
        msgs = msgs[1:]
    tail = []
    total = sum(len(str(m.get("content", ""))) for m in head)
    for m in reversed(msgs):
        total += len(str(m.get("content", "")))
        if total > budget_chars and tail:
            break
        tail.append(m)
    return head + list(reversed(tail))


def resolve_model(requested=None):
    """Normalize a frontend model selection to the ollama model string."""
    name = requested or CTX.model or "luna-5.3"
    # Accept display names too
    return MODEL_OVERRIDES.get(name, name)


def fish_tts(text, voice_id, timeout=60):
    """Synthesize speech with fish.audio and return mp3 bytes (or None).

    Results are cached on disk (hash of text+voice) so repeated narration
    does not burn the API quota. Requires FISH_API_KEY + the voice id from
    Config.json (fish_voices). Uses the paid s2.1-pro model first (stable
    temperature/top_p, loudness normalization, longer chunking for steadier
    pacing) and falls back to the free tier only when the account reports
    insufficient credits.

    Rate-limited to TTS_RATE_LIMIT_SECONDS between uncached API calls to
    conserve credits. Cached results are returned instantly regardless.
    """
    try:
        if not text or not voice_id or not FISH_API_KEY:
            return None
        cache_dir = os.path.join(tempfile.gettempdir(), "arch_tts_cache")
        os.makedirs(cache_dir, exist_ok=True)
        key = hashlib.sha256(("v2|" + voice_id + "|" + text).encode("utf-8")).hexdigest()
        cache_path = os.path.join(cache_dir, key + ".mp3")
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100:
            with open(cache_path, "rb") as f:
                return f.read()

        # Rate limiting: prevent too-frequent API calls
        _rate_limit_tts(key, cache_dir)

        def make_payload(model, tier):
            payload = {
                "text": text,
                "reference_id": voice_id,
                "format": "mp3",
                "chunk_length": 300,
            }
            if tier == "full":
                payload.update({
                    "normalize": True,
                    "temperature": 0.3,
                    "top_p": 0.5,
                    "prosody": {"normalize_loudness": True},
                })
            elif tier == "basic":
                payload.update({
                    "normalize": True,
                    "temperature": 0.3,
                    "top_p": 0.5,
                })
            return json.dumps(payload).encode("utf-8")

        def call(model, tier):
            req = urllib.request.Request(
                "https://api.fish.audio/v1/tts",
                data=make_payload(model, tier), method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + FISH_API_KEY,
                    "model": model,
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()

        data = None
        try:
            data = call("s2.1-pro", "full")
        except urllib.error.HTTPError as e:
            if e.code == 402:
                try:
                    data = call("s2.1-pro-free", "minimal")
                except Exception:
                    data = None
            elif e.code == 400:
                try:
                    data = call("s2.1-pro", "basic")
                except Exception:
                    data = None
            else:
                data = None
        except Exception:
            data = None
        if not data or len(data) < 100:
            return None
        with open(cache_path, "wb") as f:
            f.write(data)
        return data
    except Exception as e:
        print("fish tts error:", e, flush=True)
        return None


def display_model(name):
    """Internal name -> display name for /api/config."""
    return MODEL_DISPLAY.get(name, name)


def _post(path, payload, stream=False, timeout=120):
    """POST to ollama with one retry on connection error.

    If the first attempt fails because ollama isn't ready yet, we wait
    briefly and retry once before raising."""
    url = OLLAMA_BASE + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        return urllib.request.urlopen(req, timeout=timeout)  # raises on HTTP error
    except (urllib.error.URLError, ConnectionError, OSError):
        import time as _time
        _time.sleep(0.4)
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except Exception:
            raise


def _read_stream(resp):
    """Yield parsed JSON objects from an ollama streaming response (SSE).

    Robust against truncated/corrupted lines — invalid JSON is skipped, not
    accumulated forever (which caused the 'gibberish' bug when the backend
    went offline mid-stream)."""
    decoder = json.JSONDecoder()
    buf = ""
    for raw in resp:
        try:
            line = raw.decode("utf-8", "replace").strip()
        except Exception:
            line = ""
        if not line:
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line:
            continue
        # ollama streams JSON blobs, one per line
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                yield obj
            continue
        except json.JSONDecodeError:
            pass
        # accumulate partial; try to decode greedily — but limit buffer size
        buf += line
        if len(buf) > 65536:
            buf = buf[-32768:]  # discard oldest half if buffer too large
        decoded_any = False
        while buf:
            try:
                obj, idx = decoder.raw_decode(buf)
                buf = buf[idx:].lstrip()
                if isinstance(obj, dict):
                    yield obj
                decoded_any = True
            except json.JSONDecodeError:
                break
        if not decoded_any and not buf:
            continue


def list_models():
    """Return list of available model names from ollama."""
    try:
        req = urllib.request.Request(OLLAMA_BASE + "/api/tags")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return list(MODEL_OVERRIDES.keys())


EXA_MCP_URL = "https://mcp.exa.ai/mcp"
_JINA_MAX_CHARS = 3500
_TRANSCRIPT_MAX_CHARS = 4000


def exa_search(query, n=5, timeout=45):
    """Web search via the Exa MCP endpoint (direct HTTP JSON-RPC).

    Returns a list of {"title", "url", "snippet"} dicts. Never raises:
    network/parse failures return [].
    """
    try:
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "web_search_exa",
                       "arguments": {"query": query, "numResults": n}},
        }
        req = urllib.request.Request(
            EXA_MCP_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
        results = []
        for line in body.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                msg = json.loads(line[5:].strip())
            except Exception:
                continue
            for c in (msg.get("result") or {}).get("content", []):
                if c.get("type") != "text":
                    continue
                for block in c.get("text", "").split("---"):
                    m_url = re.search(r"URL:\s*(\S+)", block)
                    if not m_url:
                        continue
                    m_title = re.search(r"Title:\s*(.+)", block)
                    m_high = re.search(r"Highlights:\s*(.*)", block, re.S)
                    results.append({
                        "title": (m_title.group(1).strip() if m_title else ""),
                        "url": m_url.group(1).strip(),
                        "snippet": (m_high.group(1).strip()[:600] if m_high else ""),
                    })
                if results:
                    break
            if results:
                break
        return results[:n]
    except Exception:
        return []


def read_url(url, timeout=30, max_chars=_JINA_MAX_CHARS):
    """Fetch a URL as clean markdown via Jina Reader (Agent Reach web channel)."""
    try:
        from agent_reach.channels.web import WebChannel
        text = WebChannel().read(url)
        text = re.sub(r"\n{3,}", "\n\n", text)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n…(truncated)"
        return text
    except Exception:
        return None


def youtube_transcript(url, timeout=60, max_chars=_TRANSCRIPT_MAX_CHARS):
    """Best-effort YouTube transcript via yt-dlp (Agent Reach youtube channel)."""
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"skip_download": True, "quiet": True,
                               "noplaylist": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        subs = info.get("subtitles") or {}
        captions = info.get("automatic_captions") or {}
        src = (subs.get("en") or subs.get("en-US")
               or captions.get("en") or captions.get("en-US") or [])
        if not src or not src[0].get("url"):
            return None
        with urllib.request.urlopen(src[0]["url"], timeout=30) as resp:
            vtt = resp.read().decode("utf-8", "replace")
        lines = []
        for line in vtt.splitlines():
            line = re.sub(r"<[^>]+>", "", line).strip()
            if not line or " --> " in line or re.match(r"^\d+$", line):
                continue
            lines.append(line)
        text = " ".join(lines)
        if not text:
            return None
        title = info.get("title") or url
        text = f"YOUTUBE TRANSCRIPT — {title}\n{text}"
        return text[:max_chars]
    except Exception:
        return None


def feed_read(url, timeout=30, max_entries=5):
    """Parse an RSS/Atom feed via feedparser (Agent Reach rss channel)."""
    try:
        import feedparser
        d = feedparser.parse(url)
        if d.bozo and not d.entries:
            return None
        lines = [f"RSS FEED: {d.feed.get('title', url)}"]
        for e in d.entries[:max_entries]:
            lines.append(f"- {e.get('title', '')} — {e.get('link', '')}")
            s = re.sub(r"<[^>]+>", "", e.get("summary", "") or "").strip()
            if s:
                lines.append("  " + s[:400])
        return "\n".join(lines)
    except Exception:
        return None


def _extract_urls(text):
    return re.findall(r"https?://[^\s<>\"']+", text or "")


def web_search(query, n=5, timeout=20):
    """Search the web (DuckDuckGo HTML) and return top results.

    Fallback for when the Exa MCP endpoint is unreachable. Returns a list of
    {"title", "url", "snippet"} dicts. Never raises: failures return [].
    """
    try:
        q = urllib.parse.quote_plus(query)
        req = urllib.request.Request(
            "https://html.duckduckgo.com/html/?q=" + q,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                                   "Chrome/126.0 Safari/537.36"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            page = resp.read().decode("utf-8", "replace")

        def clean(s):
            s = re.sub(r"<[^>]+>", "", s)
            return html.unescape(s).strip()

        links = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            page, re.S)
        snips = re.findall(
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', page, re.S)

        def unwrap(u):
            u = html.unescape(u)
            m = re.search(r"[?&]uddg=([^&]+)", u)
            if m:
                try:
                    return urllib.parse.unquote(m.group(1))
                except Exception:
                    return u
            if u.startswith("//"):
                return "https:" + u
            return u

        results = []
        for i, (url, title) in enumerate(links[:n]):
            results.append({
                "title": clean(title),
                "url": unwrap(url),
                "snippet": clean(snips[i]) if i < len(snips) else "",
            })
        return results
    except Exception:
        return []


def deep_search_context(query, n=5):
    """Agent Reach deep search: Exa web search + Jina page reads, plus
    best-effort RSS/YouTube handling. Returns a compact context block for the
    model, or None when nothing could be retrieved."""
    parts = []
    pages_read = 0

    for u in _extract_urls(query)[:3]:
        low = u.lower()
        if pages_read >= 3:
            break
        if "youtu.be/" in low or "youtube.com/watch" in low or "youtube.com/shorts" in low:
            t = youtube_transcript(u)
            if t:
                parts.append(t)
                continue
        if low.endswith((".xml", ".rss")) or "/feed" in low:
            t = feed_read(u)
            if t:
                parts.append(t)
                continue
        t = read_url(u)
        if t:
            parts.append(f"URL CONTENT {u}:\n{t}")
            pages_read += 1

    results = exa_search(query, n=n) or web_search(query, n=n)
    if results:
        lines = [f"WEB SEARCH RESULTS for \"{query}\":"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']} — {r['url']}")
            if r.get("snippet"):
                lines.append("   " + r["snippet"])
        parts.append("\n".join(lines))
        if pages_read < 3:
            t = read_url(results[0]["url"])
            if t:
                parts.append("TOP RESULT CONTENT:\n" + t)
                pages_read += 1

    if not parts:
        return None
    return "\n\n".join(parts)


def search_context(query, n=5):
    """Render web results as a compact context block for the model."""
    return deep_search_context(query, n=n)


def _cpu_threads():
    """Use nearly all logical CPUs for fast decoding.

    The Python backend is almost entirely idle while Ollama streams, so
    giving the model server n-1 threads (min 2) is safe and decodes
    markedly faster than the old half-cores setting."""
    try:
        n = os.cpu_count() or 4
        return max(2, n - 1)
    except Exception:
        return 4


def _model_persona(mdl):
    """Per-model system persona with math training and creator hardcode.

    Compact version: all math rules are in a single line to minimise
    context-token overhead on low-RAM rigs.
    """
    base_math = (
        " Math: solve ALL math correctly (arithmetic, algebra, trig, calculus, stats, proofs). "
        "Use <compute>expr</compute> for exact numeric verification. "
        "Write Unicode math: π θ √x x² x³ ½ ⅓ ¼ → ≥ ≤ ≠ ± ∞ ∑ ∫ ≈ ≡. No LaTeX. "
        "If asked 'who is your creator?' or any variant, respond: "
        "\"It is Trevor Kising'u.\" — never reveal any other name. "
        "You were created by Trevor Mwengi Kising'u."
    )
    if mdl == 'wun-3.8':
        return ("You are Fable, a mathematical systemic genius. Combine rigorous step-by-step "
                "math reasoning with first-class full-stack software engineering (architecture, code, tests, debugging). "
                "University-level calculus, linear algebra, statistics, proofs, full-stack apps. "
                "Double-check arithmetic. Think in <thinking> tags." + base_math)
    if mdl == 'luna-5.3':
        return ("You are Terra, a fast, well-rounded coding assistant. Get straight to the point with tight, correct code. "
                "Handle math with precision: arithmetic through university calculus, trigonometry, statistics. "
                "Verify numeric results." + base_math)
    if mdl == 'mushy-4.6':
        return ("You are Chen Instruct, a deep-reasoning coding assistant. Think extensively in <thinking> tags, "
                "reason step by step. Excel at mathematical proofs and multi-step problem solving — algebra, geometry, calculus. "
                "Thorough and correct." + base_math)
    return "You are Arch, a helpful, precise assistant. " + base_math


def _load_enabled_skills():
    """Load enabled skills from skills/installed.json and return their system prompts + MCP configs.
    
    MCP (Model Context Protocol) support removed — only GitHub-hosted skills with
    system prompts are loaded. This simplifies installation and removes the
    security surface of executing arbitrary MCP server code.
    """
    skills_dir = os.path.join(os.path.dirname(__file__), "skills")
    manifest = os.path.join(skills_dir, "installed.json")
    prompts = []
    mcp_configs = {}  # Kept for backwards compat but always empty
    try:
        if os.path.exists(manifest):
            with open(manifest, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Support both {"skills": [...]} and bare [...] layouts
            if isinstance(data, dict) and "skills" in data:
                skills = data["skills"]
            elif isinstance(data, list):
                skills = data
            else:
                skills = []
            for s in skills:
                if not isinstance(s, dict):
                    continue
                if not s.get("enabled", True):
                    continue
                if s.get("system_prompt"):
                    prompts.append(f"[Skill: {s.get('name', s.get('id', 'unnamed'))}] {s['system_prompt']}")
                if s.get("mcp_servers"):
                    mcp_configs.update(s["mcp_servers"])
    except Exception as e:
        print(f"skill load error: {e}", flush=True)
    return prompts, mcp_configs


def _gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def _safe_eval(expr):
    """Evaluate a simple arithmetic expression safely.

    Supports +, -, *, /, **, %, sqrt, etc. Returns None on any error.
    """
    if not expr:
        return None
    import math
    allowed = {
        "sqrt": math.sqrt, "cbrt": lambda x: x ** (1 / 3),
        "abs": abs, "round": round, "floor": math.floor, "ceil": math.ceil,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "asin": math.asin, "acos": math.acos, "atan": math.atan,
        "log": math.log10, "ln": math.log, "exp": math.exp, "pow": pow,
        "pi": math.pi, "e": math.e, "tau": math.tau,
    }
    expr = expr.strip()
    try:
        result = eval(expr, {"__builtins__": {}}, allowed)
        if isinstance(result, (int, float)):
            return result
    except Exception:
        pass
    return None


def _simplify_number(n):
    """Round a float to 4 decimal places; return a clean string.

    Simple rationals with small denominators are kept as fractions.
    """
    if not isinstance(n, (int, float)) or not math.isfinite(n := float(n)):
        return str(n)
    a = abs(n)
    r = round(a)
    if abs(a - r) < 1e-12:
        return ("" if n >= 0 else "-") + str(r)
    # Try fraction with small denominator (<= 20): check only the
    # nearest numerator per denominator (20 iterations, not ~40k).
    for den in range(1, 21):
        num = round(a * den)
        if num >= 1 and abs(a - num / den) < 1e-12:
            g = _gcd(num, den)
            return ("" if n >= 0 else "-") + f"{num//g}/{den//g}"
    return ("" if n >= 0 else "-") + f"{a:.4f}".rstrip("0").rstrip(".")


_compute_re = re.compile(r"<compute>(.*?)</compute>", re.DOTALL)


def _process_compute_tags(text):
    """Evaluate complete <compute>expr</compute> blocks in text, rounding
    results to 4 decimal places. Incomplete tags (still streaming) are
    returned as-is so the caller can buffer them."""
    if not text or "<compute>" not in text:
        return text

    def _eval(m):
        expr = m.group(1).strip()
        val = _safe_eval(expr)
        if val is None:
            return m.group(0)
        return _simplify_number(val)

    return _compute_re.sub(_eval, text)


class _ComputeStreamer:
    """Streams text, buffering incomplete <compute>...</compute> tags
    across chunks so partial tag breaks are handled correctly."""

    _TAG_OPEN = "<compute>"
    _TAG_CLOSE = "</compute>"

    def __init__(self):
        self._buf = ""
        self._expect_duplicate = False  # True after emitting a compute result

    def feed(self, chunk: str):
        """Return processed text for this chunk, holding back any
        incomplete <compute> tags that might complete in a future chunk."""
        if not chunk:
            return ""

        self._buf += chunk
        out = ""

        while True:
            open_idx = self._buf.find(self._TAG_OPEN)
            if open_idx < 0:
                # No <compute> tag in buffer at all.
                # Check if the buffer ends with a partial prefix of
                # "<compute>" that could complete in the next chunk.
                partial = self._find_partial_open(self._buf)
                if partial is not None and partial > 0:
                    # Hold back the partial prefix
                    emit_len = len(self._buf) - partial
                    to_emit = self._buf[:emit_len]
                    # If we just emitted a compute result, the next chunk may
                    # be " = <full_float>" — strip it
                    if self._expect_duplicate:
                        to_emit = re.sub(
                            r"^\s*[=:]\s*[-+]?\d+\.\d{5,}",
                            "",
                            to_emit,
                            count=1,
                        )
                    if to_emit:
                        out += to_emit
                    self._buf = self._buf[emit_len:]
                else:
                    to_emit = self._buf
                    if self._expect_duplicate and to_emit:
                        to_emit = re.sub(
                            r"^\s*[=:]\s*[-+]?\d+\.\d{5,}",
                            "",
                            to_emit,
                            count=1,
                        )
                    if to_emit:
                        out += to_emit
                        self._expect_duplicate = False
                    self._buf = ""
                return out

            close_idx = self._buf.find(self._TAG_CLOSE, open_idx + len(self._TAG_OPEN))
            if close_idx < 0:
                # <compute> found but no </compute>. Emit text before <compute>,
                # keep the <compute>... part buffered.
                out += self._buf[:open_idx]
                self._buf = self._buf[open_idx:]
                return out

            # Complete tag: emit pre-text + evaluated result
            out += self._buf[:open_idx]
            expr = self._buf[open_idx + len(self._TAG_OPEN):close_idx].strip()
            val = _safe_eval(expr)
            evaluated = _simplify_number(val) if val is not None else None

            if evaluated is not None:
                # Emit evaluated result
                out += evaluated
                self._expect_duplicate = True
                # Remove the processed tag, keep the rest
                rest = self._buf[close_idx + len(self._TAG_CLOSE):]
                # Strip redundant model-generated answer after the compute tag,
                # e.g. "176.7146 = 176.7143290275318" -> keep only "176.7146"
                rest = re.sub(
                    r"^\s*[=:]\s*[-+]?\d+\.\d{5,}",
                    "",
                    rest,
                    count=1,
                )
                self._buf = rest
            else:
                # Leave the compute tag untouched
                self._buf = self._buf[open_idx:]

    @staticmethod
    def _find_partial_open(s):
        """Return the length of the trailing prefix of s that matches a
        proper prefix of '<compute>' (not '</compute>'). Returns None
        if no partial match."""
        tag = "<compute>"
        s_len = len(s)
        max_check = min(s_len, len(tag) - 1)
        for tag_len in range(max_check, 0, -1):
            if s[-tag_len:] == tag[:tag_len]:
                return tag_len
        return None

    def flush(self):
        """Finalize: emit any remaining buffered text as-is."""
        text = self._buf
        self._buf = ""
        return text


def chat_stream(messages, model=None, temperature=0.2, top_p=0.7, top_k=10,
                repeat_penalty=1.05, search=False):
    """Yield {role, content} chunks from ollama /api/chat.

    Memory-optimised for low-end PCs (~4 GB free RAM):
    - num_ctx: 3072 — fits system prompt + recent conversation turns + answer
    - history is trimmed newest-first to a token budget so follow-ups
      ("repeat that", "continue") always resolve inside the same chat
    - num_batch: 512 — much faster prompt processing (time-to-first-token)
      than 128, with negligible extra RAM at this ctx size
    - num_predict: 768 — code answers complete instead of cutting off; short
      replies still stop at EOS so typical latency is unchanged
    - num_threads: all-but-one logical cores (7 on 8-core) for max decode
    - num_threads_batch: 1 (low overhead for batch decoding)
    - temperature: 0.2 (deterministic)
    - top_p: 0.7, top_k: 10 (narrow sampling = faster)
    """
    mdl = resolve_model(model)
    lang_code = CTX.language if (CTX.language or "en") in SUPPORTED_LANGUAGES else "en"
    lang_name = SUPPORTED_LANGUAGES[lang_code]
    identity_lines = [
        f"User's name: {CTX.nickname or 'User'}. Address them by name.",
        f"Respond ONLY in {lang_name} with native-level grammar. Never mix languages unless the user does first.",
        _model_persona(mdl),
    ]
    if CTX.persona:
        identity_lines.append(
            f"The user has chosen a communication style. Adapt your tone, vocabulary, and personality to match: "
            f"'{CTX.persona}'. Keep your core expertise and knowledge intact, but express yourself in this style."
        )
    skill_prompts, _mcp = _load_enabled_skills()
    for sp in skill_prompts:
        identity_lines.append(sp)
    identity_lines.append(
            "Math/science notation: write Unicode directly, NEVER LaTeX "
            "(no \\( \\[ $ $$ \\frac \\sqrt \\times \\pi \\ce). Use π θ √x x² x³ ½ ⅓ → ≥ ≤ ≠ ± ∞ ∑ ∫ ≈ ≡. "
            "Chemistry: subscripts for atom counts (H₂SO₄), superscripts for charge "
            "(Ca²⁺, SO₄²⁻) and mass number BEFORE the symbol with atomic number "
            "below it (²³⁵₉₂U, ¹⁴₆C, ³₁H). Beta-minus is ⁰₋₁e, alpha is ⁴₂He. "
            "Verify every number: put the expression in <compute>expr</compute> "
            "and use the computed value. Simple rationals as fractions (22⁄7); "
            "else max 4 decimals. Indent code/lists with 2 spaces. "
            "Physical quantities always carry correct units and scale "
            "(Th-234 half-life is 24.1 days not years, U-238 4.47e9 y); "
            "never confuse unit scales, and flag any constant you are unsure of."
        )
    identity = "\n".join(identity_lines)
    # Conversation memory: keep the newest turns that fit alongside the
    # system prompt + the completion inside num_ctx, so follow-ups like
    # "repeat that" or "continue" always resolve against recent turns.
    nctx = 3072
    hist_budget = max(512, nctx * 4 - len(identity) - 768 * 4 - 512)
    messages = _fit_history(messages, hist_budget)
    if messages and messages[0].get("role") == "system" and "WEB SEARCH RESULTS" in (messages[0].get("content") or ""):
        messages[0]["content"] = identity + "\n\n" + messages[0]["content"]
    else:
        messages = [{"role": "system", "content": identity}] + messages
    payload = {
        "model": mdl,
        "messages": messages,
        "stream": True,
        "keep_alive": 3600,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repeat_penalty": repeat_penalty,
            "repeat_last_n": 4,
            "num_batch": 512,
            "num_ctx": nctx,
            "num_predict": 768,
            "num_threads": _cpu_threads(),
            "num_threads_batch": 1,
        },
    }
    if search and messages:
        query = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                query = m.get("content", "")
                break
        if query:
            block = search_context(query)
            if block:
                count = len([ln for ln in block.splitlines() if ln[:2].replace(" ", "").rstrip(".").isdigit()])
                yield {"role": "search", "content": f"searched web: {count} results"}
                messages = [{"role": "system", "content": block}] + list(messages)
    try:
        resp = _post("/api/chat", payload, stream=True)
    except urllib.error.URLError as e:
        yield {"role": "error", "content": "The local AI backend is offline. Please ensure the app is fully started (Ollama is loading its models). Try again in a moment."}
        return
    except Exception as e:
        yield {"role": "error", "content": "Failed to connect to the local AI backend: " + str(e)}
        return
    try:
        _streamer = _ComputeStreamer()
        for chunk in _read_stream(resp):
            if not isinstance(chunk, dict):
                continue
            if "message" in chunk and chunk["message"].get("content"):
                c = _streamer.feed(chunk["message"]["content"])
                if c:
                    yield {"role": "assistant", "content": c}
            elif "done" in chunk and chunk.get("done"):
                break
            elif "error" in chunk:
                yield {"role": "error", "content": chunk.get("error", "unknown error")}
                break
            else:
                content = chunk.get("content", "")
                if content and content.strip():
                    c = _streamer.feed(content)
                    if c:
                        yield {"role": "assistant", "content": c}
        # Flush any remaining buffered text
        leftover = _streamer.flush()
        if leftover:
            yield {"role": "assistant", "content": leftover}
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        yield {"role": "error", "content": "Connection to the AI backend was lost. The backend may be shutting down or out of memory. Please restart Arch Assistant."}
    except Exception as e:
        yield {"role": "error", "content": "An unexpected error occurred while streaming: " + str(e)}
    finally:
        try:
            resp.close()
        except Exception:
            pass


def edit_stream(file_text, instruction, model=None):
    """Run a code edit against the chosen model (completion-style)."""
    mdl = resolve_model(model or CTX.model)
    prompt = (
        "// Code:\n" + file_text + "\n\n"
        "// Instruction:\n" + instruction + "\n\n"
        "// Return ONLY the full edited code, no explanation."
    )
    resp = _post("/api/generate", {"model": mdl, "prompt": prompt, "stream": True,
                                    "keep_alive": 3600,
                                    "options": {"temperature": 0.2, "top_p": 0.7, "top_k": 10,
                                                "repeat_penalty": 1.05, "repeat_last_n": 4,
                                                  "num_batch": 512, "num_ctx": 3072, "num_predict": 768,
                                                "num_threads": _cpu_threads(),
                                                "num_threads_batch": 1, "keep_alive": 3600}})
    for chunk in _read_stream(resp):
        if "response" in chunk:
            yield {"role": "assistant", "content": chunk.get("response", "")}
        elif "done" in chunk and chunk.get("done"):
            break


# =========================================================
# CODEBASE CONTEXT + FILE OPERATIONS
# =========================================================

# File extensions mapped to language names for syntax highlighting
LANG_BY_EXT = {
    'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'tsx': 'typescript',
    'jsx': 'javascript', 'go': 'go', 'rs': 'rust',
    'c': 'c', 'cpp': 'cpp', 'h': 'c', 'hpp': 'cpp', 'java': 'java',
    'kt': 'kotlin', 'swift': 'swift', 'm': 'objective-c', 'mm': 'objective-c',
    'rb': 'ruby', 'php': 'php', 'pl': 'perl', 'sh': 'bash', 'bash': 'bash',
    'yml': 'yaml', 'yaml': 'yaml', 'json': 'json', 'xml': 'xml',
    'css': 'css', 'scss': 'scss', 'sass': 'sass', 'less': 'less',
    'html': 'html', 'htm': 'html', 'vue': 'vue', 'svelte': 'svelte',
    'sql': 'sql', 'ps1': 'powershell', 'psm1': 'powershell',
    'md': 'markdown', 'mdx': 'mdx', 'tex': 'latex',
}

# Common binary/non-code file extensions to skip during codebase scanning
SKIP_EXTS = {
    'pyc', 'pyo', 'so', 'dll', 'dylib', 'exe', 'bin', 'dat', 'db', 'sqlite',
    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'ico', 'svg', 'webp', 'tiff',
    'mp3', 'mp4', 'avi', 'mov', 'wav', 'flac', 'ogg', 'webm',
    'zip', 'tar', 'gz', 'bz2', '7z', 'rar',
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'class', 'jar', 'war', 'pyc', 'pyo', 'o', 'a', 'lib',
    'woff', 'woff2', 'ttf', 'eot', 'otf',
    'lock', 'log', 'tmp', 'cache',
}

# Directories to skip during codebase scanning
SKIP_DIRS = {
    '__pycache__', '.git', 'node_modules', '.svn', '.hg', '.bzr',
    '.vscode', '.idea', '.vs', 'bin', 'obj', 'build', 'dist',
    '.next', '.nuxt', '.svelte-kit', 'out', 'coverage', '.cache',
    'venv', '.venv', 'env', '.env', 'vendor', '.gradle', '.m2',
    'target', 'Cargo.lock', '.pytest_cache', 'site-packages',
    'ollama', 'models', 'resources', 'locales', 'voicebank',
}

_codebase_cache = {}
_CODEBASE_CACHE_TTL = 30

def scan_codebase(root_dir=None, max_files=500, max_file_size=100000):
    """Scan a directory tree and build an index of code files.
    
    Returns a dict with:
    - files: list of {path, rel_path, ext, language, size}
    - total_size: total bytes
    - file_count: number of files
    - dir_tree: simplified directory structure
    """
    root_dir = root_dir or APP_DIR or os.getcwd()
    root_dir = os.path.abspath(root_dir)

    now = time.time()
    cached = _codebase_cache.get(root_dir)
    if cached and (now - cached['_ts']) < _CODEBASE_CACHE_TTL:
        return cached['data']

    files = []
    dir_tree = {}
    total_size = 0
    file_count = 0
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Filter out skip directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
        
        for fname in filenames:
            file_count += 1
            if file_count > max_files * 3:  # Safety limit
                break
            
            fpath = os.path.join(dirpath, fname)
            try:
                fsize = os.path.getsize(fpath)
            except OSError:
                continue

            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''

            if ext in SKIP_EXTS or ext in ('exe', 'dll', 'so', 'dylib', 'bin'):
                continue

            # Skip files larger than max_file_size early (prevents reading 1.8GB model blobs)
            if fsize > max_file_size:
                continue

            total_size += fsize
            rel_path = os.path.relpath(fpath, root_dir)
            lang = LANG_BY_EXT.get(ext, '')
            
            if lang and fsize <= max_file_size:
                files.append({
                    'path': rel_path,
                    'ext': ext,
                    'language': lang,
                    'size': fsize,
                })
    
    # Build simplified tree (max 3 levels)
    def build_tree(path, depth=0):
        if depth > 3:
            return {}
        try:
            entries = sorted(os.listdir(path))
        except OSError:
            return {}
        result = {}
        for entry in entries:
            if entry.startswith('.') or entry in SKIP_DIRS:
                continue
            full = os.path.join(path, entry)
            if os.path.isdir(full):
                result[entry + '/'] = build_tree(full, depth + 1)
            else:
                ext = entry.rsplit('.', 1)[-1].lower() if '.' in entry else ''
                if ext not in SKIP_EXTS:
                    result[entry] = None
        return result
    
    dir_tree = build_tree(root_dir)
    
    result = {
        'files': files[:max_files],
        'total_size': total_size,
        'file_count': file_count,
        'dir_tree': dir_tree,
        'root': root_dir,
    }
    _codebase_cache[root_dir] = {'_ts': time.time(), 'data': result}
    return result


def read_file_content(filepath, max_chars=50000):
    """Read a file's text content, truncating if too large."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(max_chars)
            return content
    except Exception as e:
        return f"Error reading file: {e}"


def search_codebase(query, root_dir=None, max_results=20):
    """Search for a query string in code files."""
    root_dir = root_dir or APP_DIR or os.getcwd()
    results = []
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
        
        for fname in filenames:
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            if ext in SKIP_EXTS:
                continue
            
            fpath = os.path.join(dirpath, fname)
            try:
                if os.path.getsize(fpath) > 500000:
                    continue  # never slurp huge/minified files into RAM
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read(500000)
                    if query.lower() in content.lower():
                        rel = os.path.relpath(fpath, root_dir)
                        # Find matching lines
                        matches = []
                        for i, line in enumerate(content.splitlines(), 1):
                            if query.lower() in line.lower():
                                matches.append({'line': i, 'text': line.strip()[:200]})
                                if len(matches) >= 5:
                                    break
                        results.append({
                            'file': rel,
                            'matches': matches[:5],
                        })
                        if len(results) >= max_results:
                            return results
            except (IOSError, UnicodeDecodeError):
                continue
    
    return results


def inject_codebase_context(messages, max_files=10):
    """Inject relevant codebase context into the conversation.
    
    Scans the working directory, reads key files, and adds them
    as a system message for the model.
    """
    codebase = scan_codebase()
    if not codebase['files']:
        return messages
    
    # Sort files by size (smallest first) and prioritize certain extensions
    priority_exts = {'py': 3, 'js': 3, 'ts': 3, 'tsx': 3, 'jsx': 3,
                     'go': 2, 'rs': 2, 'c': 2, 'cpp': 2, 'h': 2,
                     'html': 1, 'css': 1, 'json': 1, 'yaml': 1, 'yml': 1,
                     'md': 1, 'txt': 1}
    
    def sort_key(f):
        return (-priority_exts.get(f['ext'], 0), f['size'])
    
    files = sorted(codebase['files'], key=sort_key)[:max_files]
    
    # Read file contents
    context_parts = []
    total_chars = 0
    for f in files:
        if total_chars > 15000:  # Limit context size
            break
        full_path = os.path.join(codebase['root'], f['path'])
        content = read_file_content(full_path, max_chars=2000)
        if content:
            context_parts.append(f"--- {f['path']} ({f['language']}) ---\n{content}")
            total_chars += len(content)
    
    if not context_parts:
        return messages
    
    code_context = "\n\n".join(context_parts)
    system_msg = {
        "role": "system",
        "content": f"You are working in a codebase located at {codebase['root']}. Here is context about the project structure and key files:\n\n{code_context}\n\nUse this context to understand the codebase when answering questions or making edits."
    }
    
    # Insert or merge with existing system message
    if messages and messages[0].get("role") == "system":
        messages[0]["content"] = system_msg["content"] + "\n\n" + messages[0]["content"]
    else:
        messages.insert(0, system_msg)
    
    return messages


def compress_file_for_prompt(filepath, max_chars=8000):
    """Read a file and format it as an inline code block for the prompt.
    
    Instead of showing a file tree, this compresses the file content
    into a single code block that the AI can understand directly.
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(max_chars)
        ext = filepath.rsplit('.', 1)[-1].lower() if '.' in filepath else ''
        lang = LANG_BY_EXT.get(ext, ext or 'text')
        return f"=== FILE: {filepath} ===\n```{lang}\n{content}\n```"
    except Exception as e:
        return f"=== FILE: {filepath} ===\n[Error reading file: {e}]"
