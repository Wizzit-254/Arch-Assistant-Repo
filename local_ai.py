"""
Local AI bridge: ollama HTTP client used by Api_server.

All heavy lifting talks to the portable ollama runtime on 127.0.0.1:11435.
Personality model names (luna-5.3, mushy-4.6, wun-3.8) map to display names
(Terra 5.3, Chen Instruct 3, Fable 5.1) and ollama model names (created via the .Modelfile files).
"""
import os
import re
import html
import json
import hashlib
import tempfile
import urllib.request
import urllib.error
import urllib.parse

from arch_context import OLLAMA_HOST, OLLAMA_PORT, CTX, FISH_API_KEY, APP_DIR

OLLAMA_BASE = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"

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

AFRICAN_LANGUAGE_NAMES = {
    "en": "English", "sw": "Swahili", "ha": "Hausa", "yo": "Yoruba",
    "zu": "Zulu", "ig": "Igbo", "am": "Amharic", "fr": "French",
}
AFRICAN_LANGS = set(AFRICAN_LANGUAGE_NAMES.keys())


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
        _time.sleep(1.5)
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


def chat_stream(messages, model=None, temperature=0.3, top_p=0.9, top_k=20,
                repeat_penalty=1.05, search=False):
    """Yield {role, content} chunks from ollama /api/chat.

    messages: list of {"role":"user"|"assistant"|"system","content":str}

    Speed optimizations:
    - num_batch: 128 (larger batch = faster token generation)
    - num_ctx: 4096 (shorter context = faster attention)
    - repeat_last_n: 16 (smaller window = faster)
    - temperature: 0.3 (default, can be overridden)
    """
    mdl = resolve_model(model)
    lang_name = AFRICAN_LANGUAGE_NAMES.get(CTX.language or 'en', CTX.language or 'en')
    identity_lines = [
        f"The user's preferred name is {CTX.nickname or 'User'}. Address them by that name in your replies.",
        f"Respond in the user's chosen language: {lang_name} (language code {CTX.language or 'en'}).",
        f"If the chosen language is an African language (Swahili, Hausa, Yoruba, Zulu, Igbo, Amharic, etc.), "
        f"you have native-level fluency and deep cultural understanding of these languages.",
    ]
    identity = "\n".join(identity_lines)
    messages = list(messages)
    if messages and messages[0].get("role") == "system" and "WEB SEARCH RESULTS" in (messages[0].get("content") or ""):
        messages[0]["content"] = identity + "\n\n" + messages[0]["content"]
    else:
        messages = [{"role": "system", "content": identity}] + messages
    payload = {
        "model": mdl,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repeat_penalty": repeat_penalty,
            "repeat_last_n": 16,
            "num_batch": 128,
            "num_ctx": 4096,
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
        for chunk in _read_stream(resp):
            if not isinstance(chunk, dict):
                continue
            if "message" in chunk and chunk["message"].get("content"):
                yield {"role": "assistant", "content": chunk["message"]["content"]}
            elif "done" in chunk and chunk.get("done"):
                break
            elif "error" in chunk:
                yield {"role": "error", "content": chunk.get("error", "unknown error")}
                break
            else:
                content = chunk.get("content", "")
                if content and content.strip():
                    yield {"role": "assistant", "content": content}
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
    resp = _post("/api/generate", {"model": mdl, "prompt": prompt, "stream": True})
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
    'jsx': 'javascript', 'jsx': 'javascript', 'go': 'go', 'rs': 'rust',
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
}

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
            
            total_size += fsize
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            
            if ext in SKIP_EXTS or ext in ('exe', 'dll', 'so', 'dylib', 'bin'):
                continue
            
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
    
    return {
        'files': files[:max_files],
        'total_size': total_size,
        'file_count': file_count,
        'dir_tree': dir_tree,
        'root': root_dir,
    }


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
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
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
