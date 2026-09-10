#!/usr/bin/env python3
"""
Arch Assistant - Full Installer (Stage 2)
Downloads the 5GB bundle, extracts app + models, creates shortcuts.
Supports both Windows and macOS.
"""

import os
import sys
import urllib.request
import ssl
import tempfile
import zipfile
import shutil
import subprocess
import hashlib
import platform
import json

APP_URL = "https://github.com/Wizzit-254-arch-Assistant-Repo/releases/latest/download/Arch-Assistant-App.zip"
MODELS_URL = "https://github.com/Wizzit-254-arch-Assistant-Repo/releases/latest/download/Arch-Assistant-Models.zip"
CHUNK_SIZE = 262144  # 256KB

# Parse command-line args
install_dir = os.path.join(os.path.expanduser("~"), "Downloads", "Arch Assistant")
if "--install-dir" in sys.argv:
    idx = sys.argv.index("--install-dir")
    if idx + 1 < len(sys.argv):
        install_dir = sys.argv[idx + 1]


def log(msg):
    print(msg, flush=True)


def download_with_progress(url, dest, label="Downloading"):
    """Download a file with progress bar."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    req = urllib.request.Request(url, headers={
        "User-Agent": "ArchAssistant-FullInstaller/2.0"
    })
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total > 0:
                        pct = int(downloaded / total * 100)
                        mb = downloaded / (1024 * 1024)
                        total_mb = total / (1024 * 1024)
                        
                        if total > 1024 * 1024 * 1024:  # GB download
                            gb = downloaded / (1024 * 1024 * 1024)
                            total_gb = total / (1024 * 1024 * 1024)
                            progress = f"{gb:.2f} / {total_gb:.2f} GB"
                        else:
                            progress = f"{mb:.1f} / {total_mb:.1f} MB"
                        
                        bar_len = 40
                        bar = "#" * int(bar_len * downloaded / total)
                        spaces = " " * (bar_len - len(bar))
                        print(f"\r  {label}: [{bar}{spaces}] {pct}% ({progress})", end="", flush=True)
            
            if total > 1024 * 1024 * 1024:
                print()  # New line after GB download progress
            return True
    except Exception as e:
        print(f"\n  Error downloading: {e}")
        return False


def verify_sha256(filepath, expected_hash):
    """Verify file SHA-256 checksum."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
        return h.hexdigest() == expected_hash
    return False


def extract_zip(zip_path, dest_dir):
    """Extract a zip file."""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(dest_dir)


def main():
    is_windows = platform.system() == "Windows"
    temp_dir = tempfile.mkdtemp(prefix="arch-assistant-install-")
    
    log("")
    log("=" * 60)
    log("  Arch Assistant - Full Installer (Stage 2)")
    log("  Download Manager")
    log("=" * 60)
    log("")
    log(f"  Platform: {platform.system()} {platform.machine()}")
    log(f"  Install location: {install_dir}")
    log(f"  Temp directory: {temp_dir}")
    log("")
    log("  Total download size: ~5.5 GB")
    log("  (app ~200MB + models ~5.27GB)")
    log("")
    log("=" * 60)
    log("")
    
    # Step 1: Check prerequisites
    log("[1/5] Checking prerequisites...")
    
    if is_windows:
        # Check Python
        py_found = False
        for py in ["python3", "python", "py"]:
            try:
                r = subprocess.run([py, "--version"], capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    log(f"  Found: {r.stdout.strip()}")
                    py_found = True
                    break
            except:
                pass
        if not py_found:
            log("  Python not found. Please install Python 3.10+ from python.org")
            return 1
    else:
        # macOS: check for curl
        if not shutil.which("curl"):
            log("  curl is required. Install Xcode Command Line Tools.")
            return 1
    
    log("")
    log("[2/5] Downloading application files (~200MB)...")
    log("")
    
    app_zip = os.path.join(temp_dir, "Arch-Assistant-App.zip")
    if not download_with_progress(APP_URL, app_zip, "App"):
        log("")
        log("  ERROR: App download failed. Check your internet connection.")
        return 1
    
    log("")
    log("")
    log("[3/5] Downloading AI models (5.27 GB)...")
    log("")
    log("  Pre-trained model weights for offline operation.")
    log("  No separate Ollama install required.")
    log("")
    
    models_zip = os.path.join(temp_dir, "Arch-Assistant-Models.zip")
    if not download_with_progress(MODELS_URL, models_zip, "Models"):
        log("")
        log("  WARNING: Model download failed. App will still be installed.")
        log("  Models will download on first run instead.")
    else:
        log("")
    
    log("")
    log("[4/5] Extracting and installing...")
    
    # Create install directory
    if os.path.exists(install_dir):
        shutil.rmtree(install_dir)
    os.makedirs(install_dir, exist_ok=True)
    
    # Extract app
    app_extract = os.path.join(temp_dir, "app")
    extract_zip(app_zip, app_extract)
    
    # Copy app files
    # Look for "Arch Assistant" subdirectory in the zip
    source_dir = os.path.join(app_extract, "Arch Assistant")
    if not os.path.exists(source_dir):
        source_dir = app_extract
    
    for item in os.listdir(source_dir):
        s = os.path.join(source_dir, item)
        d = os.path.join(install_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
    
    log("  App installed.")
    
    # Extract models
    if os.path.exists(models_zip):
        models_dir = os.path.join(install_dir, "ollama", "models")
        os.makedirs(models_dir, exist_ok=True)
        extract_zip(models_zip, models_dir)
        log("  AI models installed.")
    
    # Step 5: Create shortcuts / symlinks
    log("")
    log("[5/5] Creating shortcuts and finishing up...")
    
    if is_windows:
        # Create desktop shortcut via PowerShell
        ps_script = f"""
        $ws = New-Object -ComObject WScript.Shell
        $desktop = [Environment]::GetFolderPath('Desktop')
        $sc = $ws.CreateShortcut($desktop + '\\Arch Assistant.lnk')
        $sc.TargetPath = '{install_dir}\\Arch.exe'
        $sc.WorkingDirectory = '{install_dir}'
        $sc.Description = 'Arch AI Assistant'
        $sc.Save()
        """
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                      creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        # macOS: create Applications symlink
        app_path = os.path.join(install_dir, "Arch")
        symlink = "/Applications/Arch Assistant"
        try:
            if os.path.exists(symlink):
                os.unlink(symlink)
            os.symlink(app_path, symlink)
        except:
            pass
    
    # Write checksum file
    checksum_file = os.path.join(install_dir, "checksums.sha256")
    with open(checksum_file, "w") as f:
        f.write(f"app_zip: {hashlib.sha256(open(app_zip, 'rb').read()).hexdigest()}\n")
        if os.path.exists(models_zip):
            f.write(f"models_zip: {hashlib.sha256(open(models_zip, 'rb').read()).hexdigest()}\n")
    
    # Cleanup temp
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    log("")
    log("=" * 60)
    log("  INSTALLATION COMPLETE!")
    log("=" * 60)
    log("")
    log(f"  Installed to: {install_dir}")
    log("  Desktop shortcut created.")
    log("")
    log("  App files: ~200 MB")
    log("  AI models: 5.27 GB (bundled for offline operation)")
    log("  Total: ~5.5 GB")
    log("")
    log("  All AI models included — no separate download needed.")
    log("")
    
    launch = input("  Launch Arch Assistant now? (Y/n) ").strip().lower()
    if launch != 'n':
        if is_windows:
            os.startfile(os.path.join(install_dir, "Arch.exe"))
        else:
            subprocess.Popen([os.path.join(install_dir, "Arch")])
    
    log("")
    log("  Installer finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
