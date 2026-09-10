# Arch Assistant - macOS Installer Builder

## Overview

This directory contains the tools and scripts for building the macOS installer for Arch Assistant.

## Prerequisites

- **macOS 10.15+** (Intel or Apple Silicon)
- **Xcode Command Line Tools** (includes `hdiutil`, `pkgbuild`, etc.)
- **Homebrew** (optional, for additional tools)
- **GitHub CLI** (`gh`) for uploading releases

## Build Steps

1. **Clone this repo on macOS:**
   ```bash
   git clone https://github.com/Wizzit-254/Arch-Assistant-Repo.git
   cd Arch-Assistant-Repo
   ```

2. **Download the app zip from GitHub releases:**
   ```bash
   curl -L -o Arch-Assistant-App.zip \
     https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/Arch-Assistant-App.zip
   ```

3. **Run the build script:**
   ```bash
   chmod +x build-macos-installer.sh
   ./build-macos-installer.sh
   ```

4. **Upload to GitHub Release:**
   ```bash
   gh release upload v1.0.0 ArchAssistant.dmg
   gh release upload v1.0.0 ArchAssistant-Installer-macOS.pkg
   ```

## What This Produces

- **`Arch.app`** — A proper macOS application bundle
- **`ArchAssistant-Installer-macOS.pkg`** — A PKG installer with a guided wizard
- **`ArchAssistant.dmg`** — A disk image containing the PKG installer for distribution

## Manual .app Creation

If you want to create just the `.app` bundle without the PKG/DMG:

```bash
mkdir -p Arch.app/Contents/{MacOS,Resources}
cp main.js Arch.app/Contents/MacOS/Arch
cp -R index.html resources ollama voicebank skills locales Arch.app/Contents/Resources/
chmod +x Arch.app/Contents/MacOS/Arch
```

Then create `Info.plist`:
```bash
cat > Arch.app/Contents/Info.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Arch Assistant</string>
    <key>CFBundleIdentifier</key><string>com.arch.assistant</string>
    <key>CFBundleVersion</key><string>1.0.0</string>
    <key>CFBundleExecutable</key><string>Arch</string>
</dict>
</plist>
EOF
```

## Notarization (Apple Silicon)

For Apple Silicon Macs, you may want to notarize the DMG:

```bash
xcrun notarytool submit ArchAssistant.dmg \
  --keychain-profile "AC_PASSWORD" \
  --wait
```

## Files in this Directory

- `build-macos-installer.sh` — Main build script for PKG + DMG
- `README.md` — This file

## Notes

- The app uses Python for backend logic, so macOS must have Python 3 installed
- For full offline operation, the 5GB Ollama models are bundled in `Arch-Assistant-App.zip`
- The installer creates a guided wizard (PKG) experience for users
