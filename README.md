# Arch Assistant

A portable offline AI desktop assistant with 3 persona models powered by Ollama.

## Quick Install

### Windows 10 / 11 (x64)
1. Download `ArchAssistantSetup-x64.exe` from the [latest release](https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest)
2. Run it — the wizard opens instantly and lets you choose your models and install folder:
   - Terra 5.3 / Chen-Instruct 3 (3B) — ~1.7 GB
   - Fable 5.1 (7B) — ~3.3 GB
3. The wizard downloads only the models you tick. Downloads are resumable: cancel at any time and run the installer again to the same folder to continue. Installs at copy speed.
4. Launch Arch Assistant from your desktop.

### macOS 11+
Download `ArchAssistant-macOS.command` from the [releases page](https://github.com/Wizzit-254/Arch-Assistant-Repo/releases) and run it — it builds `Arch.app` for Intel and Apple Silicon.

That's it. No Python setup, no Ollama install — the installer handles everything.

## Requirements

- Windows 10/11 (x64) or macOS 11+
- ~6 GB free disk space with both models installed (5.3 GB), plus working space during setup
- Internet connection for the model downloads during setup — fully offline after that

## AI Models

| Model | Base | Size | Specialty |
|-------|------|------|-----------|
| **Terra 5.3** | 3B | ~1.7 GB (shared pack) | Fast, code-first assistant |
| **Chen Instruct 3** | 3B | ~1.7 GB (shared pack) | Deep reasoning, multi-step problems |
| **Fable 5.1** | 7B | ~3.3 GB | Large codebases, long-context refactors |

Terra 5.3 and Chen-Instruct 3 share one 3B base (qwen2.5-coder:3b-instruct-q4_K_S).
Fable 5.1 is a separate 7B model (qwen2.5-coder:7b-instruct-q3_K_S).

## Features

- Real-time streaming chat (SSE)
- Web search integration (DuckDuckGo + Exa MCP)
- Speech-to-text via Web Speech API (Google Cloud)
- Text-to-speech (Fish Audio API + system TTS)
- Codebase context injection
- Dark/Light theme
- Chat history persistence — conversation memory across the full chat history
- Multi-language support (English, Kiswahili, French, Mandarin, Japanese, Arabic)
- Math simplification — all numeric results rounded to 4 decimal places or simplified to fractions
- Skill system — embedded reasoning protocols (Math Olympiad, Anti-Hallucination, Critical Thinking, Iterative Refinement, Verification)
- Idle-stop watchdog — automatically stops Ollama after 10 minutes of inactivity to save RAM
- Clean shutdown — kills all Ollama processes when the app closes; lazily restarts on next use
- System identity — all models respond "It is Trevor Kising'u" when asked about their creator

## For Developers

### Source Code Structure

```
Arch Assistant/
├── api_server.py          # HTTP API server (port 9224)
├── local_ai.py            # Ollama client, web search, TTS
├── ollama_runtime.py      # Portable Ollama lifecycle
├── arch_context.py        # Config loader, runtime context
├── speech_stt.ps1         # Legacy PowerShell STT (deprecated; Web Speech API used in renderer)
├── Config.json            # App configuration
├── *.Modelfile            # Ollama model definitions
├── Arch.exe               # Electron frontend
├── ollama/                # Portable Ollama runtime
│   ├── ollama.exe
│   ├── lib/ollama/        # llama.cpp server + DLLs
│   └── models/            # Model weights (blobs + manifests)
└── resources/app.asar     # Electron renderer
```

### Building from Source

```bash
# Install dependencies
pip install PyGithub  # For release packaging

# Create a release
python create_release.py --token YOUR_TOKEN --owner YOUR_USERNAME --tag v1.0.0
```

### Running Locally

```bash
cd "Arch Assistant"
python api_server.py
# Open Arch.exe or navigate to http://127.0.0.1:9224
```

## License

MIT
