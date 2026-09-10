#!/bin/bash
# Arch Assistant - macOS Full Installer (Stage 2)
# Stage 2 of 3: Download Manager
# Downloads the app bundle + 5GB AI models and installs

set -e

echo ""
echo "  ============================================================"
echo "           ARCH ASSISTANT - macOS FULL INSTALLER"
echo "           Stage 2: Download Manager"
echo "  ============================================================"
echo ""

APP_URL="https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/Arch-Assistant-macOS-universal.zip"
MODELS_URL="https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/Arch-Assistant-Models-macOS.zip"
INSTALL_DIR="$HOME/Applications/Arch Assistant"
TEMP_DIR=$(mktemp -d /tmp/arch-assistant-install-XXXXXX)

echo "  This will install Arch Assistant to:"
echo "    $INSTALL_DIR"
echo ""
echo "  Total download size: ~5.5 GB (app ~200MB + models ~5.27GB)"
echo "  Internet needed once for setup — after that, fully offline."
echo ""
echo "  ============================================================"
echo ""

read -p "  Proceed with installation? (Y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]] && [[ ! -z $REPLY ]]; then
    echo "  Installation cancelled."
    rm -rf "$TEMP_DIR"
    exit 0
fi

echo ""
echo "  [1/4] Checking for Python 3..."
echo ""

if command -v python3 &>/dev/null; then
    python3 --version
elif command -v python &>/dev/null; then
    python --version
else
    echo "  Python 3 is required but not found."
    echo "  Install via: brew install python"
    echo "  Or download from: https://python.org/downloads/"
    rm -rf "$TEMP_DIR"
    exit 1
fi

echo ""
echo "  [2/4] Downloading application files (~200MB)..."
echo ""

curl -L -o "$TEMP_DIR/Arch-Assistant-macOS.zip" "$APP_URL" --retry 3 --retry-delay 5 --progress-bar

if [ $? -ne 0 ]; then
    echo ""
    echo "  -----------------------------------------------"
    echo "  App download failed. Check your internet."
    echo "  -----------------------------------------------"
    rm -rf "$TEMP_DIR"
    exit 1
fi

echo "  App download complete."

echo ""
echo "  [3/4] Downloading AI models (5.27 GB)..."
echo ""
echo "  This downloads pre-trained model weights for offline operation."
echo "  No separate Ollama install required."
echo ""

curl -L -o "$TEMP_DIR/Arch-Assistant-Models.zip" "$MODELS_URL" --retry 3 --retry-delay 5 --progress-bar

if [ $? -ne 0 ]; then
    echo ""
    echo "  -----------------------------------------------"
    echo "  Model download failed. App will still be installed"
    echo "  but models will download on first run instead."
    echo "  -----------------------------------------------"
else
    echo ""
    echo "  Models download complete."
fi

echo ""
echo "  [4/4] Installing..."
echo ""

if [ ! -d "$INSTALL_DIR" ]; then
    mkdir -p "$INSTALL_DIR"
fi

# Extract app
unzip -o "$TEMP_DIR/Arch-Assistant-macOS.zip" -d "$TEMP_DIR/app" 2>/dev/null

if [ -d "$TEMP_DIR/app/Arch Assistant" ]; then
    cp -R "$TEMP_DIR/app/Arch Assistant/"* "$INSTALL_DIR/"
else
    cp -R "$TEMP_DIR/app/"* "$INSTALL_DIR/" 2>/dev/null || true
fi

# Extract models if downloaded
if [ -f "$TEMP_DIR/Arch-Assistant-Models.zip" ]; then
    echo "  Extracting AI models..."
    mkdir -p "$INSTALL_DIR/ollama/models"
    unzip -o "$TEMP_DIR/Arch-Assistant-Models.zip" -d "$INSTALL_DIR/ollama/models" 2>/dev/null
fi

# Make app executable
chmod +x "$INSTALL_DIR/Arch"

# Create symlink in Applications
echo "  Creating Applications symlink..."
ln -sf "$INSTALL_DIR/Arch" "/Applications/Arch Assistant" 2>/dev/null || true

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "  ============================================================"
echo "             INSTALLATION COMPLETE"
echo "  ============================================================"
echo ""
echo "  Installed to: $INSTALL_DIR"
echo "  Symlinked to: /Applications/Arch Assistant"
echo ""
echo "  App files: ~200 MB"
echo "  AI models: 5.27 GB (bundled for offline operation)"
echo "  Total: ~5.5 GB"
echo ""
echo "  All AI models included — no separate download needed after install."
echo ""

read -p "  Launch Arch Assistant now? (Y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
    if [ -f "$INSTALL_DIR/Arch" ]; then
        open "$INSTALL_DIR/Arch" 2>/dev/null || "$INSTALL_DIR/Arch" &
    fi
fi

echo ""
echo "  Installer finished."
read -p "Press Enter to exit..."
