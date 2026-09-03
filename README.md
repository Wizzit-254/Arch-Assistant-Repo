# Arch Assistant

A portable offline AI desktop assistant with 3 persona models powered by Ollama.

![Arch](ArchAssistantInstaller.exe)

## Quick Install

### Option 1: Lightweight Installer (Recommended)
1. Download `ArchAssistantInstaller.exe` from the [latest release](https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest)
2. Run the installer — it downloads the full app automatically (choose install location)
3. Launch Arch Assistant from your desktop

### Option 2: Direct ZIP Download
When you visit the [releases page](https://github.com/Wizzit-254/Arch-Assistant-Repo/releases), the `Arch-Assistant-App.zip` is directly downloadable. Extract the folder and run `Arch.exe`.

### Option 3: install.bat
1. Download `install.bat` from this repo
2. Run it — it downloads the full app automatically
3. Launch Arch Assistant from your desktop

That's it. No Python setup, no Ollama install — the installer handles everything.

## Requirements

- Windows 10/11
- Python 3.10+ (the installer downloads it automatically if missing)
- ~3 GB free disk space (includes base model blob, ~1.8 GB)
- Internet connection needed only for first launch model verification

## AI Models

| Model | Specialty | Speed |
|-------|-----------|-------|
| **Terra 5.3** | Fast, code-first assistant | Fast |
| **Chen Instruct 3** | Deep reasoning, multi-step problems | Medium |
| **Kyuu 3.8** | Large codebases, long-context refactors | Medium |

All models share one base: **Fable 5.1** (Qwen 2.5 Coder 3B, quantized Q4_K_S). The models are included in the release zip for fully offline operation.

## Features

- Real-time streaming chat (SSE)
- Web search integration (DuckDuckGo + Exa MCP)
- Speech-to-text via Web Speech API (Google Cloud)
- Text-to-speech (Fish Audio API + system TTS)
- Codebase context injection
- Dark/Light theme
- Chat history persistence
- Multi-language support (English + African languages)

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
