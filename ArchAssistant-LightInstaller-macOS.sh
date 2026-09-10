#!/bin/bash
# Arch Assistant - macOS Lightweight Installer
# Stage 1 of 3: Bootstrap Loader (~7MB)
# Downloads Stage 2 (medium installer) which then downloads the 5GB bundle

set -e

echo ""
echo "  ============================================================"
echo "           ARCH ASSISTANT - macOS INSTALLER"
echo "           Stage 1: Bootstrap Loader"
echo "  ============================================================"
echo ""
echo "  This lightweight installer (~7MB) will download the"
echo "  full installer which includes 5GB of AI models."
echo ""
echo "  ============================================================"
echo ""

STAGE2_URL="https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/ArchAssistant-Stage2-macOS.sh"
TEMP_DIR=$(mktemp -d /tmp/arch-assistant-XXXXXX)
STAGE2_SCRIPT="$TEMP_DIR/ArchAssistant-Stage2-macOS.sh"

echo "  [1/3] Downloading full installer (Stage 2)..."
echo ""

# Download with progress
curl -L -o "$STAGE2_SCRIPT" "$STAGE2_URL" --retry 3 --retry-delay 5

if [ ! -f "$STAGE2_SCRIPT" ]; then
    echo ""
    echo "  -----------------------------------------------"
    echo "  Stage 2 download failed."
    echo "  Please check your internet connection."
    echo "  Or download manually from:"
    echo "  https://github.com/Wizzit-254/Arch-Assistant-Repo/releases"
    echo "  -----------------------------------------------"
    echo ""
    read -p "Press Enter to exit..."
    rm -rf "$TEMP_DIR"
    exit 1
fi

echo "  Stage 2 downloaded successfully."
echo ""

echo "  [2/3] Launching full installer (Stage 2)..."
echo ""

chmod +x "$STAGE2_SCRIPT"
"$STAGE2_SCRIPT"

echo "  [3/3] Cleaning up..."
rm -rf "$TEMP_DIR"

echo ""
echo "  ============================================================"
echo "  Installation process complete."
echo "  Stage 2 installer handled the 5GB model download and install."
echo "  ============================================================"
echo ""
read -p "Press Enter to exit..."
