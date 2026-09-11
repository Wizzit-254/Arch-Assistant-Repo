#!/bin/bash
#
# Arch Assistant — macOS installer wizard (v1.0.0)
# Double-click behavior: run `chmod +x ArchAssistant-macOS.command` once,
# then double-click. Or run:  bash ArchAssistant-macOS.command
#
# What it does (guided, ~7GB free needed during setup):
#   1. Welcome + license acceptance
#   2. Chooses install location (default ~/ArchAssistant)
#   3. Downloads the mac app bundle (~1.9GB, resumes on bad wifi)
#   4. Downloads the matching Electron runtime + Ollama for your chip
#   5. Assembles Arch.app, signs it ad-hoc, links it into Applications
#   6. Launches Arch on first run (models load in background)
#
set -u

APP_VERSION="1.0.0"
REPO="https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/download/v1.0.0"
PAYLOAD_URL="$REPO/Arch-Assistant-App-macOS.zip"
ELECTRON_VER="v44.3.0"
OLLAMA_URL="https://github.com/ollama/ollama/releases/download/v0.12.9/ollama-darwin.tgz"

say()  { printf "\n\033[1m%s\033[0m\n" "$1"; }
info() { printf "  %s\n" "$1"; }
die()  { printf "\nERROR: %s\n" "$1" >&2; exit 1; }

# ---------- 0. Preconditions ----------
command -v python3 >/dev/null || die "python3 is required (macOS ships it — if missing, install Xcode command line tools: xcode-select --install)."
command -v curl >/dev/null || die "curl is required."
ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ]; then E_ARCH="arm64"; else E_ARCH="x64"; fi
ELECTRON_URL="https://github.com/electron/electron/releases/download/$ELECTRON_VER/electron-$ELECTRON_VER-darwin-$E_ARCH.zip"

say "Arch Assistant $APP_VERSION — macOS setup"
info "Detected chip: $ARCH  (runtime: darwin-$E_ARCH)"
info "You need about 7GB free during setup (5GB app + downloads)."
info "Downloads resume automatically if wifi drops — just leave it running."
echo ""
read -r -p "Continue? [Y/n] " go
case "${go:-Y}" in [Yy]*) ;; *) exit 0;; esac

# ---------- 1. License ----------
say "License (MIT) + Terms"
cat <<'EOF'
  Arch Assistant is free, open-source software (MIT License).
  Source: https://github.com/Wizzit-254/Arch-Assistant-Repo
  Provided AS IS, no warranty. AI output may be wrong — verify it.
  Prompts stay on your machine; narration uses fish.audio if configured.
EOF
echo ""
read -r -p "Accept and install? [Y/n] " acc
case "${acc:-Y}" in [Yy]*) ;; *) exit 0;; esac

# ---------- 2. Location ----------
say "Install location"
echo ""
read -r -p "Install to [$HOME/ArchAssistant]: " dest
DEST="${dest:-$HOME/ArchAssistant}"
mkdir -p "$DEST" || die "cannot create $DEST"
FREE_KB="$(df -k "$DEST" | tail -1 | awk '{print $4}')"
if [ "${FREE_KB:-0}" -lt 7340032 ]; then
  die "not enough free space (need ~7GB). Free up space and re-run."
fi
info "Installing to: $DEST"
cd "$DEST" || die "cannot enter $DEST"

# ---------- 3. App bundle (resumable, retry forever) ----------
say "Downloading Arch app files (~100MB)…"
curl -L -C - --retry 999 --retry-delay 5 --retry-all-errors --retry-connrefused \
     -o "Arch-Assistant-App-macOS.zip" "$PAYLOAD_URL" \
  || die "download failed. Re-run this script to resume."
[ -s "Arch-Assistant-App-macOS.zip" ] || die "download produced an empty file."

say "Extracting…"
python3 -c "import zipfile; zipfile.ZipFile('Arch-Assistant-App-macOS.zip').extractall('Arch-Assistant-App-macOS')" \
  || die "extraction failed (re-run to retry)."
APP_SRC="$DEST/Arch-Assistant-App-macOS"
[ -f "$APP_SRC/index.html" ] || die "payload looks wrong (index.html missing)."

# ---------- 4. Runtimes for this chip ----------
say "Downloading Electron runtime for $E_ARCH (~125MB)…"
curl -L -C - --retry 999 --retry-delay 5 --retry-all-errors \
     -o "electron.zip" "$ELECTRON_URL" || die "Electron download failed."
say "Downloading Ollama for macOS (~24MB)…"
curl -L -C - --retry 999 --retry-delay 5 --retry-all-errors \
     -o "ollama-darwin.tgz" "$OLLAMA_URL" || die "Ollama download failed."

# ---------- 5. Assemble Arch.app ----------
say "Assembling Arch.app…"
rm -rf "Arch.app" "Electron.app" __MACOSX
python3 -c "import zipfile; zipfile.ZipFile('electron.zip').extractall('.')" \
  || die "Electron unzip failed."
[ -d "Electron.app" ] || die "Electron.app missing after unzip."
rm -rf "Arch.app"
mv "Electron.app" "Arch.app"
mkdir -p "Arch.app/Contents/Resources/app"
for f in index.html main.js package.json api_server.py local_ai.py arch_context.py ollama_runtime.py \
         Luna.Modelfile Mushy.Modelfile Wun.Modelfile Config.json \
         Fable-5.1.mp4 Arch-icon.png Arch.png; do
  [ -e "$APP_SRC/$f" ] && cp -R "$APP_SRC/$f" "Arch.app/Contents/Resources/app/"
done
for d in voicebank skills ollama; do
  [ -d "$APP_SRC/$d" ] && cp -R "$APP_SRC/$d" "Arch.app/Contents/Resources/app/"
done

# Ollama darwin binary into ollama/
tar -xzf "ollama-darwin.tgz" -C "Arch.app/Contents/Resources/app/ollama/" \
  || die "Ollama unpack failed."
chmod +x "Arch.app/Contents/Resources/app/ollama/ollama"

# ---------- 5b. Models: pull bases + create Arch models (visible progress) ----------
say "Setting up AI models (~5GB, one-time)…"
export OLLAMA_MODELS="$DEST/Arch.app/Contents/Resources/app/ollama/models"
export OLLAMA_HOST="127.0.0.1:11435"
mkdir -p "$OLLAMA_MODELS"
"$DEST/Arch.app/Contents/Resources/app/ollama/ollama" serve >/dev/null 2>&1 &
OLLAMA_PID=$!
for i in $(seq 1 20); do
  curl -sf "http://127.0.0.1:11435/api/tags" >/dev/null 2>&1 && break
  sleep 1
done
OL="$DEST/Arch.app/Contents/Resources/app/ollama/ollama"
MF="$DEST/Arch.app/Contents/Resources/app"
"$OL" pull "qwen2.5-coder:3b-instruct-q4_K_S" || die "model pull failed (check internet)."
"$OL" pull "qwen2.5-coder:7b-instruct-q3_K_S" || die "model pull failed (check internet)."
"$OL" create "luna-5.3"   -f "$MF/Luna.Modelfile"  || die "'create luna-5.3' failed."
"$OL" create "mushy-4.6"  -f "$MF/Mushy.Modelfile" || die "'create mushy-4.6' failed."
"$OL" create "wun-3.8"    -f "$MF/Wun.Modelfile"   || die "'create wun-3.8' failed."
kill "$OLLAMA_PID" 2>/dev/null || true
info "Models ready."
python3 - "$APP_SRC" <<'EOF'
import plistlib, sys
pl = "Arch.app/Contents/Info.plist"
with open(pl, "rb") as f:
    d = plistlib.load(f)
d["CFBundleName"] = "Arch"
d["CFBundleDisplayName"] = "Arch"
d["CFBundleIdentifier"] = "com.arch.assistant"
if sys.argv[1:]:
    import os
    if os.path.exists("Arch.app/Contents/Resources/app/Arch-icon.png"):
        d["CFBundleIconFile"] = "Arch"
with open(pl, "wb") as f:
    plistlib.dump(d, f)
print("Info.plist branded.")
EOF
if [ -f "Arch.app/Contents/Resources/app/Arch-icon.png" ]; then
  sips -s format icns "Arch.app/Contents/Resources/app/Arch-icon.png" \
       --out "Arch.app/Contents/Resources/Arch.icns" >/dev/null 2>&1 || true
fi

# Clear quarantine + ad-hoc sign so Gatekeeper lets it open
xattr -cr "Arch.app" 2>/dev/null || true
codesign --force --deep --sign - "Arch.app" 2>/dev/null || info "(ad-hoc sign skipped — first launch: right-click Arch.app > Open)"

# Applications link (user dir: no sudo needed)
mkdir -p "$HOME/Applications"
ln -sfn "$DEST/Arch.app" "$HOME/Applications/Arch.app"
info "Linked: $HOME/Applications/Arch.app"

# Cleanup big downloads (keep payload zip? No — free the space)
rm -f "electron.zip" "ollama-darwin.tgz" "Arch-Assistant-App-macOS.zip"
rm -rf "Arch-Assistant-App-macOS" __MACOSX

say "Done! Arch is installed."
info "Open it from Applications (first launch: right-click > Open, once)."
info "The AI models load in the background — first answer takes ~1 min,"
info "then it stays fast. Requires internet once for model setup."
echo ""
read -r -p "Launch Arch now? [Y/n] " launch
case "${launch:-Y}" in [Yy]*) open "$DEST/Arch.app";; *) ;; esac
