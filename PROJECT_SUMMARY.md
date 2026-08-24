# Arch Assistant: Building a Fully Offline AI Desktop Assistant

## Inspiration

The idea for **Arch Assistant** came from a simple frustration: every AI assistant today requires an internet connection, sends your data to the cloud, and stops working the moment your Wi-Fi drops. I wanted to build something different — a **private, offline AI assistant** that runs entirely on your own hardware, with no data ever leaving your machine.

The name "Arch" was chosen as a tribute to Arch Linux, representing the philosophy of **user control, simplicity, and transparency**. Just as Arch puts the user in full control of their operating system, Arch Assistant puts you in full control of your AI.

The core question driving this project was:

> *What if your AI assistant was truly yours — downloaded once, running locally, with zero recurring fees and zero privacy compromise?*

---

## What I Learned

This project was a masterclass in **systems integration**. I learned to bridge three fundamentally different technology stacks into one cohesive product:

### 1. Electron + HTML/CSS/JS (Frontend)
I learned to build desktop applications using **Electron**, creating a native-feeling UI with web technologies. The frontend communicates with the backend via a **Chrome DevTools Protocol (CDP)** bridge running on `127.0.0.1:9224`, giving the JavaScript layer direct control over the Electron BrowserWindow.

### 2. Python (Backend & AI Logic)
The backend is a **Python HTTP server** that handles:
- Ollama process lifecycle management (start/stop/health monitoring)
- AI model routing and chat streaming via Server-Sent Events (SSE)
- Config persistence and dynamic model switching

I learned the importance of **process isolation** — the Python backend manages Ollama as a child process, ensuring clean startup/shutdown even if the AI engine crashes.

### 3. Ollama (AI Runtime)
Ollama serves as the local AI inference engine. I learned to:
- Manage model manifests and blob storage manually
- Configure custom `OLLAMA_HOST` and `OLLAMA_MODELS` paths for portability
- Parse Modelfiles to customize model behavior and system prompts
- Implement **Server-Sent Events (SSE)** streaming for real-time token-by-token response delivery

### 4. Software Packaging & Distribution
I learned to create:
- A **C# installer** (compiled with the legacy .NET Framework 4.0 `csc.exe`) that downloads and extracts the application
- A **batch file installer** with a real-time progress bar for wider compatibility
- Portable Ollama bundling with selective model pruning to minimize archive size

---

## How I Built It

### Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  Arch Assistant                     │
│                                                     │
│  ┌──────────────┐    CDP Bridge     ┌────────────┐  │
│  │   Electron    │◄────────────────►│  Python    │  │
│  │   Frontend    │  127.0.0.1:9224  │  Backend   │  │
│  │  (HTML/JS)    │                  │  (HTTP)    │  │
│  └──────────────┘                   └─────┬──────┘  │
│                                           │         │
│                                    SSE Stream       │
│                                           │         │
│                                    ┌──────▼──────┐  │
│                                    │   Ollama    │  │
│                                    │  127.0.0.1  │  │
│                                    │  :11435     │  │
│                                    └─────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Step 1: The Portable Ollama Bundle
The first challenge was making Ollama **portable**. Ollama normally installs to `%LOCALAPPDATA%` and stores models in a fixed location. I solved this by:

1. Copying the system `ollama.exe` into the app directory
2. Setting environment variables at runtime:
   ```python
   os.environ["OLLAMA_HOST"] = "127.0.0.1:11435"
   os.environ["OLLAMA_MODELS"] = os.path.join(app_dir, "ollama", "models")
   ```
3. Creating custom Modelfiles with embedded system prompts for each AI persona

This made the entire AI stack **self-contained** — no system installation required.

### Step 2: The Three AI Models
I created three distinct AI personalities, each based on `qwen2.5-coder:3b-instruct-q4_K_M`:

| Model | Purpose | System Prompt Focus |
|-------|---------|-------------------|
| **Luna 5.3** | General assistant | Helpful, friendly, conversational |
| **Mushy 4.6** | Creative & emotional | Warm, empathetic, expressive |
| **Wun 3.8** | Technical & analytical | Precise, logical, code-focused |

Each model is defined by a `.Modelfile` that sets the base model, temperature, and a custom system prompt:

```dockerfile
FROM qwen2.5-coder:3b-instruct-q4_K_M
PARAMETER temperature 0.7
SYSTEM """
You are Mushy, a warm and expressive AI assistant...
"""
```

### Step 3: The Real-Time Streaming Backend
The Python backend implements a streaming architecture:

```python
@app.route("/api/chat", methods=["POST"])
def chat():
    messages = request.json["messages"]
    model = request.json.get("model", "luna-5.3")
    
    def generate():
        stream = ollama_client.chat(model=model, messages=messages, stream=True)
        for chunk in stream:
            token = chunk["message"]["content"]
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"
    
    return Response(generate(), mimetype="text/event-stream")
```

The frontend consumes this via the `EventSource` API, rendering tokens as they arrive — giving the user the same "typing" feel as cloud AI services, but running entirely locally.

### Step 4: The Installer
The distribution problem was solved with a two-stage approach:

1. **GitHub Release** hosts the ~130 MB application archive (all binaries, no model blobs)
2. **Bootstrap installer** (`install.bat`) handles download, extraction, and setup

The installer uses PowerShell's `System.Net.WebClient` with a custom progress bar:

```powershell
$bar = '[' + ('#' * $pct) + ('-' * (100 - $pct)) + ']'
Write-Host "`r  Downloading: $bar $pct% ($mb / $totalMb MB)" -NoNewline
```

---

## Challenges Faced

### Challenge 1: The Model Blob Problem
Ollama stores AI models as content-addressed blobs. Each 3B parameter model is ~2 GB. Shipping all models meant a **5 GB+ archive**.

**Solution:** I pruned the model storage to keep only the three active models (`luna-5.3`, `mushy-4.6`, `wun-3.8`), removing unused blobs and the deleted `arch-a-2.2` model. This reduced the archive from **5 GB to 130 MB** — models download on first launch instead.

The model storage follows Ollama's structure:
```
ollama/models/
├── manifests/
│   └── registry.ollama.ai/
│       └── library/
│           ├── luna-5.3/
│           │   └── latest
│           ├── mushy-4.6/
│           │   └── latest
│           └── wun-3.8/
│               └── latest
└── blobs/
    └── sha256-<hash>    (shared base model blobs)
```

### Challenge 2: Git LFS Misconfiguration
I initially configured Git LFS to track `*.exe` files, thinking the installer needed special handling. This caused the **installer to become an LFS pointer file** instead of a real executable — users downloading it would get a 1 KB text file, not a 12.5 KB program.

**Solution:** Changed `.gitattributes` to only LFS-track `*.zip` files:
```
*.zip filter=lfs diff=lfs merge=lfs -text
```

### Challenge 3: Windows Defender False Positives
The unsigned C# `.exe` installer triggered SmartScreen and antivirus warnings on every Windows machine. Even though the code was harmless (it only downloads a zip file), the unsigned executable pattern matched malware heuristics.

**Solution:** Replaced the `.exe` with a `.bat` file that calls PowerShell internally. Batch files don't trigger the same heuristics. The PowerShell code uses `System.Net.WebClient` — a standard .NET class — rather than custom network code.

### Challenge 4: TLS/SSL Certificate Errors
The original installer used `WebClient`, which failed on some systems with SSL certificate errors when connecting to GitHub's CDN.

**Solution:** Switched to `HttpWebRequest` with explicit TLS 1.2 configuration:
```csharp
ServicePointManager.SecurityProtocol = 
    SecurityProtocolType.Tls12 | SecurityProtocolType.Tls11 | SecurityProtocolType.Tls;
```

### Challenge 5: Archive Structure Mismatch
The installer expected a root folder named `Arch Assistant` inside the zip, but the archive was created with files at the root level. This caused the "Archive did not contain 'Arch Assistant' folder" error.

**Solution:** Recreated the zip with explicit structure:
```
Arch-Assistant-App.zip
└── Arch Assistant/       ← Required root folder
    ├── Arch.exe
    ├── api_server.py
    ├── ollama/
    └── ...
```

---

## Technical Specifications

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Frontend | Electron + HTML/CSS/JS | Desktop UI shell |
| Backend | Python 3.10+ | HTTP API server, process management |
| AI Engine | Ollama 0.x | Local LLM inference |
| Models | Qwen 2.5 Coder 3B (Q4_K_M) | Language model backbone |
| Installer | Batch + PowerShell | Download and setup |
| Distribution | GitHub Releases | Asset hosting |

### Key Metrics
- **Archive size:** 130 MB (without AI models)
- **Full install size:** ~300 MB (with models downloaded)
- **RAM usage:** ~2 GB (with one model loaded)
- **First launch model download:** ~2 GB
- **Response latency:** < 500ms to first token (local inference)

---

## What's Next

- [ ] **Auto-updater** — Check for new releases on startup
- [ ] **Plugin system** — Allow custom tools and extensions
- [ ] **Multi-model loading** — Keep multiple models in memory simultaneously
- [ ] **Voice I/O** — Whisper.js for speech-to-text, local TTS
- [ ] **Cross-platform** — Linux and macOS builds using the same portable Ollama approach

---

*Built with persistence, curiosity, and a belief that AI should be accessible to everyone — not just those with fast internet and cloud subscriptions.*
