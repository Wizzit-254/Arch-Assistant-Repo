# Arch Assistant

A portable offline AI desktop assistant with 3 persona models powered by Ollama.

![Arch](Arch-Assistant-Installer.exe)

## Quick Install

1. **Download** `install.bat` from this repo
2. **Run** the installer — it downloads the full app automatically
3. **Launch** Arch Assistant from your desktop
4. **Wait** for AI models to download on first launch (~2 GB)

That's it. No Python setup, no Ollama install — the installer handles everything.

## Requirements

- Windows 10/11
- Python 3.10+ (for the backend)
- ~3 GB free disk space
- Internet connection (for initial model download)

## AI Models

| Model | Specialty | Speed |
|-------|-----------|-------|
| **Luna 5.3** | Fast, code-first assistant | Fast |
| **Mushy 4.6** | Deep reasoning, multi-step problems | Medium |
| **Wun 3.8** | Large codebases, long-context refactors | Medium |

All models are based on Qwen 2.5 Coder 3B (quantized Q4_K_S).

## Features

- Real-time streaming chat (SSE)
- Web search integration (DuckDuckGo + Exa MCP)
- Speech-to-text (Windows SAPI)
- Text-to-speech (Fish Audio API)
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
├── speech_stt.ps1         # Windows speech-to-text
├── Config.json            # App configuration
├── *.Modelfile            # Ollama model definitions
├── Arch.exe               # Electron frontend
├── ollama/                # Portable Ollama runtime
│   ├── ollama.exe
│   ├── lib/ollama/        # llama.cpp server + DLLs
│   └── models/            # Model weights
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
