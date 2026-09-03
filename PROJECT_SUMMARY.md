# Arch Assistant: Building a Fully Offline AI Desktop Assistant

## Inspiration

The idea for **Arch Assistant** was born from a simple frustration with the status quo of AI assistants. Every major AI service today—ChatGPT, Claude, Gemini—requires:

1. A constant internet connection
2. Sending your data to remote servers
3. Ongoing subscription fees
4. Dependency on service uptime

What if an AI assistant could be **yours**? Downloaded once, running entirely on your local machine, with zero recurring costs and zero privacy compromise? That's the question that drove every design decision in Arch Assistant.

The name "Arch" draws from two inspirations:
- **Arch Linux** — the philosophy of user control, simplicity, and transparency
- **Architecture** — the structural design of software systems that bridge multiple layers

## What I Learned

Building Arch Assistant was a deep dive into **systems integration** across four fundamentally different technology stacks:

### Electron + JavaScript (Frontend)
I learned to build desktop applications using **Electron**, where the renderer process (a Chromium browser) communicates with the backend through a local HTTP API on `127.0.0.1:9224`. The key insight was using the **Chrome DevTools Protocol (CDP)** bridge pattern—Electron spawns a Python backend process that serves HTTP, and the frontend makes AJAX calls to it.

### Python (Backend)
The backend runs on Python's standard library only (`http.server`, `urllib.request`, `subprocess`, `json`) because:
- No `pip install` needed — runs on any system Python
- Minimal dependencies reduce attack surface
- Easy to debug and extend

Key patterns I implemented:
- **Server-Sent Events (SSE)** for streaming AI responses token-by-token
- **ThreadingHTTPServer** for concurrent request handling
- **Process management** to start/stop the Ollama runtime as a subprocess

### Ollama (AI Runtime)
Ollama serves as the local LLM inference engine. I learned to:
- Run it in **portable mode** by setting `OLLAMA_HOST=127.0.0.1:11435` and `OLLAMA_MODELS` to a local directory
- Manage model manifests (`.Modelfile` files with custom system prompts)
- Handle **content-addressed blob storage** where model weights are stored as `sha256-<hash>` files

### Voice & Narration (TTS/STT)
I learned the difference between:

$$\text{Cloud TTS (Fish.Audio)} \rightarrow \text{High quality, requires API key}$$
$$\text{Browser TTS (speechSynthesis)} \rightarrow \text{Always available, lower quality}$$

The voice system uses a **fallback chain**: try Fish.Audio TTS API first (for premium voices), fall back to browser `speechSynthesis` if the API fails. Each voice maps to a Fish.Audio voice ID:

| Voice Name | Fish.Audio ID | Browser Voice Mapping |
|---|---|---|
| Verity | `8d21b053...` | Microsoft Zira (en-US) |
| Light | `8e577d80...` | Microsoft David (en-US) |
| L | `52d9d3c3...` | Microsoft Mark (en-US) |
| Sabrina | `4cf07afc...` | Microsoft Zira (en-US) |
| Chinese Voice | `95880cb6...` | Microsoft Xiaoxiao (zh-CN) |

### Software Packaging
I learned the complexities of distributing Windows applications:
- **Git LFS** for large assets (model blobs can be gigabytes)
- **GitHub Releases** as a CDN for the application archive
- **Batch file installers** instead of unsigned `.exe` to avoid antivirus false positives
- **Portable design** so the entire app can run from a USB drive

## How I Built It

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                Arch Assistant (Desktop App)             │
├─────────────────────────────────────────────────────────┤
│  Electron Frontend (Chromium)                           │
│    - index.html (UI, chat, voice settings)              │
│    - main.js (process management, window creation)      │
│    - voicebank/*.mp3 (voice preview samples)            │
│    - CDP Bridge: http://127.0.0.1:9224                  │
├─────────────────────────────────────────────────────────┤
│  Python Backend (portable, stdlib only)                 │
│    - api_server.py (HTTP server, SSE streaming)         │
│    - local_ai.py (Ollama client, model routing)         │
│    - ollama_runtime.py (process lifecycle)              │
│    - arch_context.py (config, paths, context)           │
│    - *.Modelfile (AI personality definitions)           │
│    - speech_stt.ps1 (SAPI dictation for voice input)    │
├─────────────────────────────────────────────────────────┤
│  Ollama Runtime (portable)                              │
│    - ollama.exe (local LLM server)                      │
│    - models/ (base model + persona manifests)            │
│    - lib/ollama/ (CPU backend DLLs)                     │
├─────────────────────────────────────────────────────────┤
│  Electron Binaries                                      │
│    - Arch.exe (main executable)                         │
│    - *.dll (Chromium/Electron runtime libraries)        │
│    - *.pak (locale/resource packs)                      │
└─────────────────────────────────────────────────────────┘
```

### AI Model Architecture

The system is built on **Qwen 2.5 Coder 3B** (Q4_K_M quantization), which provides:

- **Parameters**: ~3 billion
- **VRAM requirement**: ~2 GB minimum
- **Context window**: 4,096 tokens (optimized for speed)
- **Quantization**: 4-bit (Q4_K_M) — reduces from ~6 GB to ~2 GB

Three AI personas share one base model:

$$\text{Base Model} = \text{qwen2.5-coder:3b-instruct-q4\_K\_M}$$

$$\text{Persona}_i = \text{create(Base Model, Modelfile}_i\text{)}$$

Where each `Modelfile` injects a custom system prompt:

```dockerfile
# Luna.Modelfile (display: Terra 5.3)
FROM qwen2.5-coder:3b-instruct-q4_K_M
PARAMETER temperature 0.3
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.05
SYSTEM """
You are Luna, a helpful coding assistant...
"""
```

### Voice Narration Pipeline

```
User clicks "Narrate" button
         ↓
speakOutLoud(text)
         ↓
voices.find(name === selectedVoice) → finds Fish.Audio voice ID
         ↓
speakFish(text, voiceId)
    Calls POST /api/tts {text, voice_id}
         ↓
Backend: fish_tts(text, voiceId)
    - Checks cache: sha256(voiceId|text) → temp/arch_tts_cache/
    - If cached: returns cached mp3
    - If not: calls https://api.fish.audio/v1/tts
    - Tries s2.1-pro first, falls back to s2.1-pro-free
         ↓
Audio plays via HTML5 Audio element
```

### STT (Speech-to-Text) Pipeline

```
User clicks "Voice Input" button
         ↓
listenOnce(duration)
         ↓
POST /api/stt {duration: 5}
         ↓
Backend: Calls speech_stt.ps1
    - Uses .NET System.Speech.Recognition
    - SAPI dictation grammar
    - Recognizes speech via default audio device
    - Returns recognized text
         ↓
Text inserted into input field
```

### Streaming Chat Architecture

The chat system uses **Server-Sent Events (SSE)** for real-time token delivery:

```
Frontend: POST /api/chat {messages, model, temperature}
         ↓
Backend: local_ai.chat_stream(messages)
         ↓
POST /api/chat (Ollama)
         ↓
SSE stream → yield {"role":"assistant","content":"..."}
         ↓
Frontend: EventSource processes each token
         ↓
Text rendered character by character
```

The streaming math:

$$t_{total} = \sum_{i=1}^{n} t_{token_i} + t_{network}$$

$$\text{Latency}_{first} = t_{prompt} + t_{first\_token}$$

Where prompt processing is parallelizable but token generation is sequential:

$$t_{generate} = n \times t_{token} \approx n \times \frac{1}{tokens/second}$$

For Qwen 2.5 3B on a mid-range CPU:

$$tokens/second \approx 15-30 \text{ (CPU only, Q4)}$$

$$t_{response} \approx \frac{n_{tokens}}{20} \text{ seconds}$$

## Challenges Faced

### 1. The Model Blob Problem

Ollama stores model weights as content-addressed blobs. Each 3B parameter model is ~2 GB. Including all model variants meant a **5 GB+** archive.

**Solution:** I pruned the blob storage to keep only the three active personas and the shared base model. Removed unused variants and old model versions:

```
Before: 5.2 GB (all model variants + blobs)
After:  337 MB (3 personas + base model skeleton, no blobs)
Final:  ~126 MB (compressed zip for distribution)
```

The models download on first run (background, ~2 GB total):

$$Size_{distribution} = \sum_{files \neq blobs} size_{file} = 126 \text{ MB}$$

$$Size_{runtime} = Size_{distribution} + \sum_{models} size_{blob}$$

### 2. Git LFS Misconfiguration

I initially tracked `*.exe` files with Git LFS, thinking the large Electron binary needed special handling. This caused the **installer to become a 128-byte LFS pointer** instead of a real executable—users would download a text file, not a program.

**Lesson learned:** LFS tracking rules can silently corrupt your releases. The fix:

```gitattributes
# BEFORE (broken):
*.exe filter=lfs diff=lfs merge=lfs -text

# AFTER (fixed):
*.zip filter=lfs diff=lfs merge=lfs -text
```

### 3. Antivirus False Positives

The unsigned C# `.exe` installer triggered SmartScreen and antivirus warnings on every Windows machine—a common problem with unsigned executables that download and extract files.

**Solution:** Replaced the `.exe` with a `.bat` file that calls PowerShell internally:
- Batch files are not flagged by AV heuristics
- PowerShell's `System.Net.WebClient` is a standard .NET class
- No dynamic code execution patterns

### 4. The ffmpeg.dll Error

When users ran `Arch.exe` directly (without the installer), Electron would crash with:

> "The code execution cannot proceed because ffmpeg.dll was not found."

This happens because:
1. Electron's DLL search path depends on the **current working directory**
2. Running as administrator changes the working directory to `C:\Windows\System32`
3. The `ffmpeg.dll` couldn't be found

**Solution:**
1. The installer sets the shortcut's `WorkingDirectory` to the app folder
2. The install.bat installs to `%USERPROFILE%\Downloads\Arch Assistant` (no admin needed)
3. All DLLs are bundled in the same directory as `Arch.exe`

### 5. TLS/SSL Certificate Issues

The original installer used `WebClient`, which failed on some systems with SSL certificate validation errors when connecting to GitHub's CDN.

**Fix:** Switched to `HttpWebRequest` with explicit TLS 1.2:

```csharp
ServicePointManager.SecurityProtocol = 
    SecurityProtocolType.Tls12 | 
    SecurityProtocolType.Tls11 | 
    SecurityProtocolType.Tls;
```

### 6. The "UI Prototype" Fallback Message

During development, a placeholder `replySimulated()` function returned:

> "Thanks for the details — this is a UI prototype, so this reply is simulated, but the flow (new chat → history → reopen) is fully wired up."

This was meant as a development fallback but appeared when the backend AI wasn't responding. Fixed by providing a helpful error message instead, so users know to check if Ollama is running.

### 7. Git History & Token Security

During development, GitHub tokens were shared in the development environment. After all work was complete, all tokens were **revoked** and the git history was checked for any accidentally committed secrets.

## Technical Specifications

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Frontend** | Electron + HTML/CSS/JS | Desktop UI shell (~172 MB) |
| **Backend** | Python 3.10+ (stdlib only) | HTTP API, process management |
| **AI Engine** | Ollama (portable) | Local LLM inference |
| **Models** | Qwen 2.5 Coder 3B (Q4_K_M) | Language model backbone |
| **Voices** | Fish.Audio API + Web Speech API | Text-to-speech narration |
| **STT** | Windows SAPI / .NET Speech | Speech-to-text input |
| **Installer** | Batch + PowerShell | Download, extract, configure |
| **Distribution** | GitHub Releases (126 MB) | Application archive hosting |

### Performance Metrics

| Metric | Value |
|--------|-------|
| Distribution size | 126 MB (zip) |
| Full install size | ~350 MB (without models) |
| With AI models | ~2.3 GB (3 personas + base) |
| RAM usage (idle) | ~500 MB |
| RAM usage (chatting) | ~1.5-2 GB |
| First token latency | ~5-15 seconds (model load) |
| Steady-state token rate | 15-30 tokens/sec (CPU) |
| Voice narration latency | ~2-5 seconds (TTS) |

## What's Next

- [ ] **Auto-updater** — Check for new releases on startup
- [ ] **GPU acceleration** — CUDA support for faster inference
- [ ] **Plugin system** — Allow custom tools and extensions
- [ ] **Multi-model support** — Switch between different base models
- [ ] **Voice commands** — Wake word detection + voice-only control
- [ ] **Mobile companion** — Remote access to the local AI from phone

## Key Files

| File | Purpose |
|------|---------|
| `install.bat` | Bootstrap installer (no admin, auto Python check) |
| `Arch.exe` | Electron executable (bundles Chromium) |
| `api_server.py` | Python HTTP server (CDP-style bridge on :9224) |
| `local_ai.py` | Ollama client, streaming chat, TTS/STT |
| `ollama_runtime.py` | Portable Ollama process management |
| `arch_context.py` | Config loader, paths, runtime context |
| `*.Modelfile` | AI personality definitions (Terra 5.3, Chen Instruct 3, Kyuu 3.8) |
| `speech_stt.ps1` | PowerShell STT script using SAPI (deprecated, replaced by Web Speech API) |
| `index.html` | Frontend UI (HTML + CSS + JS, ~180K lines) |
| `main.js` | Electron main process (window, backend spawn) |
| `voicebank/*.mp3` | Voice preview samples for settings |
| `ollama/` | Bundled Ollama runtime + base model manifests |

*Built with persistence, curiosity, and a belief that AI should be accessible to everyone — not just those with fast internet and cloud subscriptions.*
