#!/bin/bash
#
# Arch Assistant - macOS Installer Package Builder (.pkg)
# 
# Prerequisites:
#   - macOS 10.15+ (Intel or Apple Silicon)
#   - The Arch-Assistant-App.zip release asset
#   - Apple Developer ID certificate (for signing)
#
# Usage:
#   1. Download App from GitHub:
#      curl -L -o Arch-Assistant-App.zip \
#        https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/Arch-Assistant-App.zip
#
#   2. Extract the App bundle:
#      python3 -c "import zipfile; zipfile.ZipFile('Arch-Assistant-App.zip').extractall('.')"
#
#   3. Create a proper .app bundle:
#      mkdir -p Arch.app/Contents/MacOS
#      mkdir -p Arch.app/Contents/Resources
#      cp main.js Arch.app/Contents/MacOS/Arch
#      cp -R index.html Arch.app/Contents/Resources/
#      cp -R resources Arch.app/Contents/Resources/
#      cp -R ollama Arch.app/Contents/Resources/
#      cp -R voicebank Arch.app/Contents/Resources/
#      cp -R skills Arch.app/Contents/Resources/
#      cp -R locales Arch.app/Contents/Resources/
#
#   4. Make the main executable:
#      chmod +x Arch.app/Contents/MacOS/Arch
#
#   5. Create Info.plist:
#      (see below)
#
#   6. Build the PKG:
#      productbuild --root Arch.app /tmp/ArchAssistant-Installer-root \
#        --sign "Developer ID Installer: YOUR NAME" \
#        ArchAssistant-Installer-macOS.pkg
#
#   7. Create the DMG:
#      hdiutil create -volname "Arch Assistant Installer" \
#        -srcfolder ArchAssistant-Installer-macOS.pkg \
#        -ov -format UDZO ArchAssistant.dmg
#
#   8. Upload to GitHub:
#      gh release upload v1.0.0 ArchAssistant.dmg
#

set -e

APP_NAME="Arch Assistant"
APP_BUNDLE="Arch.app"
PKG_NAME="ArchAssistant-Installer-macOS.pkg"
DMG_NAME="ArchAssistant.dmg"
INSTALL_DIR="/Applications/Arch Assistant"

echo "=== Arch Assistant macOS Package Builder ==="
echo ""

# Check prerequisites
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "ERROR: This script must be run on macOS"
    exit 1
fi

if [ ! -f "Arch-Assistant-App.zip" ]; then
    echo "Downloading Arch-Assistant-App.zip..."
    curl -L -o Arch-Assistant-App.zip \
        "https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/Arch-Assistant-App.zip"
fi

echo "Extracting app files..."
python3 -c "import zipfile; zipfile.ZipFile('Arch-Assistant-App.zip').extractall('temp-extract')" 2>/dev/null

# Create .app bundle structure
echo "Creating .app bundle..."
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# Copy files from extraction
EXTRACT_DIR=""
if [ -d "temp-extract/Arch Assistant" ]; then
    EXTRACT_DIR="temp-extract/Arch Assistant"
elif [ -d "temp-extract" ]; then
    EXTRACT_DIR="temp-extract"
fi

if [ -z "$EXTRACT_DIR" ] || [ ! -d "$EXTRACT_DIR" ]; then
    echo "ERROR: Could not find extracted app files"
    exit 1
fi

# Copy all app files to Resources
cp -R "$EXTRACT_DIR/index.html" "$APP_BUNDLE/Contents/Resources/"
cp -R "$EXTRACT_DIR/main.js" "$APP_BUNDLE/Contents/Resources/"
cp -R "$EXTRACT_DIR/package.json" "$APP_BUNDLE/Contents/Resources/" 2>/dev/null || true
cp -R "$EXTRACT_DIR/api_server.py" "$APP_BUNDLE/Contents/Resources/" 2>/dev/null || true
cp -R "$EXTRACT_DIR/local_ai.py" "$APP_BUNDLE/Contents/Resources/" 2>/dev/null || true
cp -R "$EXTRACT_DIR/ollama_runtime.py" "$APP_BUNDLE/Contents/Resources/" 2>/dev/null || true
cp -R "$EXTRACT_DIR/arch_context.py" "$APP_BUNDLE/Contents/Resources/" 2>/dev/null || true

# Copy directories
for dir in resources ollama voicebank skills locales; do
    if [ -d "$EXTRACT_DIR/$dir" ]; then
        cp -R "$EXTRACT_DIR/$dir" "$APP_BUNDLE/Contents/Resources/"
    fi
done

# Copy the main.js as the executable entry point
cp "$APP_BUNDLE/Contents/Resources/main.js" "$APP_BUNDLE/Contents/MacOS/Arch"
chmod +x "$APP_BUNDLE/Contents/MacOS/Arch"

# Create Info.plist
cat > "$APP_BUNDLE/Contents/Info.plist" << 'PListEnd'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Arch Assistant</string>
    <key>CFBundleDisplayName</key>
    <string>Arch Assistant</string>
    <key>CFBundleIdentifier</key>
    <string>com.arch.assistant</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>Arch</string>
    <key>CFBundleIconFile</key>
    <string>ArchAssistant.icns</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSAppleEventsUsageDescription</key>
    <string>Allow Arch Assistant to control this Mac?</string>
    <key>NSCameraUsageDescription</key>
    <string>Arch Assistant needs camera access for video features.</string>
    <key>NSMicrophoneUsageDescription</key>
    <string>Arch Assistant needs microphone access for voice input.</string>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright (c) 2026 Wizzit. All rights reserved.</string>
</dict>
</plist>
PListEnd

# Clean up
rm -rf temp-extract

echo "✓ Created $APP_BUNDLE"
echo ""

# Create PKG installer
echo "Creating PKG installer..."
mkdir -p installer-root/Applications
cp -R "$APP_BUNDLE" "installer-root/Applications/"

# Create a simple distribution XML
DISTRIBUTION_PLIST="/tmp/ArchAssistantDistribution.plist"
cat > "$DISTRIBUTION_PLIST" << 'DListEnd'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PackageVersion</key>
    <string>1.0</string>
</dict>
</plist>
DListEnd

# Build the package
pkgbuild --root "installer-root" \
         --identifier "com.arch.assistant.installer" \
         --version "1.0.0" \
         --install-location "/" \
         --distribution "$DISTRIBUTION_PLIST" \
         "$PKG_NAME"

echo "✓ Created $PKG_NAME"
echo ""

# Create DMG
echo "Creating DMG..."
if [ -f "$DMG_NAME" ]; then
    rm "$DMG_NAME"
fi

# Create a temporary DMG with the PKG
hdiutil create -volname "Arch Assistant Installer" \
    -srcfolder "$PKG_NAME" \
    -ov -format UDZO "$DMG_NAME"

echo "✓ Created $DMG_NAME"
echo ""

# Verify the DMG
echo "Verifying DMG..."
hdiutil verify "$DMG_NAME"

echo ""
echo "=== Build complete ==="
echo "Files created:"
echo "  $APP_BUNDLE (app bundle for manual installation)"
echo "  $PKG_NAME (guided installer package)"
echo "  $DMG_NAME (disk image with PKG installer)"
echo ""
echo "Upload to GitHub:"
echo "  gh release upload v1.0.0 $DMG_NAME"
echo "  gh release upload v1.0.0 $PKG_NAME"
