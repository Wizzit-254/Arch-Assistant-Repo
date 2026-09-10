#!/usr/bin/env python3
"""
Arch Assistant - Staged Installer (Stage 1)
Small installer (~10MB) with UI for T&C display and install location.
Downloads and runs Stage 2 which fetches the 5GB model bundle.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import urllib.request
import ssl
import os
import sys
import tempfile
import subprocess
import hashlib

# --- Config ---
STAGE2_URL = "https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/Arch-Assistant-Models.zip"
APP_URL = "https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/Arch-Assistant-App.zip"
APP_NAME = "Arch Assistant"
CHUNK_SIZE = 262144  # 256KB

# --- Terms & Conditions ---
TERMS_TEXT = """
ARCH ASSISTANT - TERMS AND CONDITIONS
Version 1.0.0 (Effective: September 10, 2026)

1. LICENSE
   This software is distributed under the MIT License.
   - You may use, copy, modify, merge, publish, distribute, sublicense,
     and/or sell copies of the Software.
   - The above copyright notice and this permission notice shall be
     included in all copies or substantial portions.
   - THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

2. NO WARRANTY
   This is free, open-source software. We provide NO warranty
   (express or implied) regarding its fitness for any purpose.
   Use at your own risk.

3. AI MODEL DISCLAIMER
   The bundled AI models are provided as-is. Generated output
   is not guaranteed to be accurate, secure, or original.
   Always review AI-generated code before using it.

4. PRIVACY
   Arch Assistant is designed to be self-hosted. No data or
   prompts are transmitted to the internet during normal operation.
   No telemetry, no tracking, no accounts required.
   No personal information is collected, stored, or transmitted.

5. SUPPORT
   Community support is available via GitHub Issues:
   https://github.com/Wizzit-254/Arch-Assistant-Repo/issues
   Contact: trevorkisingu@gmail.com

6. INSTALLATION
   This installer will:
   - Download ~5GB of AI model files
   - Extract them to your chosen install directory
   - Create a desktop shortcut
   - Launch the app when complete

7. DOWNLOAD SECURITY
   Installers are served over HTTPS with HSTS.
   Official download location:
   https://github.com/Wizzit-254/Arch-Assistant-Repo/releases

8. BY CLICKING "INSTALL", YOU AGREE TO THESE TERMS.

9. THIRD-PARTY COMPONENTS
   This software bundles models from Ollama (Apache 2.0) and
   various open-source libraries. See the LICENSE file in the
   installation directory for details.

10. EXPORT COMPLIANCE
    By downloading, you agree to comply with your country's
    export control laws and regulations.
"""


class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} Installer")
        self.root.geometry("620x560")
        self.root.resizable(False, False)
        
        # Set dark theme colors
        self.root.configure(bg="#1a1a22")
        
        # Variables
        self.install_path = tk.StringVar()
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        self.install_path.set(os.path.join(default_dir, APP_NAME))
        
        # Initialize window position AFTER update_idletasks
        self.root.update_idletasks()
        screen_width = self.root.winfo_screen_width()
        screen_height = self.root.winfo_screen_height()
        x = (screen_width // 2) - (620 // 2)
        y = (screen_height // 2) - (560 // 2)
        self.root.geometry(f"+{x}+{y}")
        
        self.setup_ui()
        
    def setup_ui(self):
        # Header
        header = tk.Frame(self.root, bg="#1a1a22")
        header.pack(fill=tk.X, padx=30, pady=(20, 0))
        
        tk.Label(header, text=f"{APP_NAME} Installer",
                font=("Segoe UI", 16, "bold"), fg="white", bg="#1a1a22").pack(anchor=tk.W)
        tk.Label(header, text="Two-stage installer • ~10MB bootstrap",
                font=("Segoe UI", 9), fg="#888", bg="#1a1a22").pack(anchor=tk.W, pady=(4, 0))
        
        # T&C Section
        tc_frame = tk.LabelFrame(self.root, text=" Terms & Conditions ",
                                font=("Segoe UI", 9), fg="#aaa", bg="#25252f",
                                borderwidth=1, relief=tk.SOLID)
        tc_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=15)
        
        self.tc_text = scrolledtext.ScrolledText(tc_frame, wrap=tk.WORD,
                                                font=("Segoe UI", 8),
                                                bg="#1a1a22", fg="#ccc",
                                                insertbackground="white",
                                                height=12, width=70,
                                                state=tk.DISABLED)
        self.tc_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.tc_text.config(state=tk.NORMAL)
        self.tc_text.insert(tk.END, TERMS_TEXT)
        self.tc_text.config(state=tk.DISABLED)
        self.tc_text.yview(tk.END)
        
        # Accept checkbox
        self.accept_var = tk.BooleanVar()
        accept_cb = tk.Checkbutton(self.root, text="I have read and agree to the Terms & Conditions",
                                  variable=self.accept_var, font=("Segoe UI", 9),
                                  fg="white", bg="#1a1a22", selectcolor="#25252f",
                                  activebackground="#1a1a22", activeforeground="white")
        accept_cb.pack(anchor=tk.W, padx=30, pady=5)
        
        # Install location
        loc_frame = tk.Frame(self.root, bg="#1a1a22")
        loc_frame.pack(fill=tk.X, padx=30, pady=10)
        
        tk.Label(loc_frame, text="Install location:",
                font=("Segoe UI", 9), fg="white", bg="#1a1a22").pack(anchor=tk.W)
        
        path_row = tk.Frame(loc_frame, bg="#1a1a22")
        path_row.pack(fill=tk.X, pady=(5, 0))
        
        self.path_entry = tk.Entry(path_row, textvariable=self.install_path,
                                  font=("Segoe UI", 9), bg="#25252f", fg="white",
                                  insertbackground="white", relief=tk.FLAT,
                                  highlightbackground="#444", highlightthickness=1,
                                  width=50)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        
        browse_btn = tk.Button(path_row, text="Browse",
                              command=self.browse_location,
                              font=("Segoe UI", 9), bg="#25252f", fg="white",
                              activebackground="#333", activeforeground="white",
                              relief=tk.FLAT, padx=12, pady=4)
        browse_btn.pack(side=tk.RIGHT)
        
        # Status / Progress
        self.status_label = tk.Label(self.root, text="",
                                    font=("Segoe UI", 9), fg="#888", bg="#1a1a22")
        self.status_label.pack(pady=5)
        
        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill=tk.X, padx=30, pady=5)
        
        # Buttons
        btn_frame = tk.Frame(self.root, bg="#1a1a22")
        btn_frame.pack(fill=tk.X, padx=30, pady=15)
        
        self.install_btn = tk.Button(btn_frame, text="Install",
                                    command=self.start_install,
                                    font=("Segoe UI", 10, "bold"), bg="#4a90d9",
                                    fg="white", activebackground="#3a7bc8",
                                    relief=tk.FLAT, padx=20, pady=8)
        self.install_btn.pack(side=tk.RIGHT, padx=(8, 0))
        
        quit_btn = tk.Button(btn_frame, text="Cancel",
                            command=self.root.quit,
                            font=("Segoe UI", 10), bg="#25252f",
                            fg="white", activebackground="#333",
                            relief=tk.FLAT, padx=20, pady=8)
        quit_btn.pack(side=tk.RIGHT)
        
        # Progress bar styling
        style = ttk.Style()
        style.configure("TProgressbar",
                       background="#25252f", thickness=6)
        style.map("TProgressbar", background=[('active', '#4a90d9')])
        
    def browse_location(self):
        path = filedialog.askdirectory(
            title="Select install directory",
            initialdir=os.path.dirname(self.install_path.get())
        )
        if path:
            self.install_path.set(os.path.join(path, APP_NAME))
    
    def update_progress(self, value, text=""):
        self.progress["value"] = value
        if text:
            self.status_label.config(text=text)
        self.root.update_idletasks()
    
    def start_install(self):
        if not self.accept_var.get():
            messagebox.showerror("Error", "You must accept the Terms & Conditions to proceed.")
            return
        
        install_dir = self.install_path.get().strip()
        if not install_dir:
            messagebox.showerror("Error", "Please specify an install location.")
            return
        
        if ".." in install_dir or (":" not in install_dir and not install_dir.startswith("/")):
            messagebox.showerror("Error", "Please choose a valid install path.")
            return
        
        self.install_btn.config(state=tk.DISABLED)
        
        thread = threading.Thread(target=self.do_install, args=(install_dir,), daemon=True)
        thread.start()
    
    def do_install(self, install_dir):
        try:
            os_info = platform.system()
            is_windows = os_info == "Windows"
            
            # Step 1: Download app files
            self.update_progress(0, "Downloading app files (~200MB)...")
            app_zip = os.path.join(tempfile.gettempdir(), "Arch-Assistant-App.zip")
            if not self.download_with_progress(APP_URL, app_zip, "App"):
                self.update_progress(0, "Download failed. Check internet connection.")
                self.install_btn.config(state=tk.NORMAL)
                return
            
            # Step 2: Download AI models (5.27GB)
            self.update_progress(30, "Downloading AI models (5.27 GB)...")
            models_zip = os.path.join(tempfile.gettempdir(), "Arch-Assistant-Models.zip")
            if not self.download_with_progress(MODELS_URL if MODELS_URL else STAGE2_URL, models_zip, "Models"):
                self.update_progress(0, "Model download failed. App will still be installed.")
                # Continue with app-only install
            
            # Step 3: Extract and install
            self.update_progress(80, "Extracting and installing...")
            self.extract_and_install(app_zip, models_zip, install_dir, is_windows)
            
            # Step 4: Create shortcuts
            self.create_shortcuts(install_dir, is_windows)
            
            self.update_progress(100, "Installation complete!")
            
            self.root.after(100, lambda: self.show_done_message())
            
        except Exception as e:
            self.update_progress(0, f"Error: {str(e)}")
            self.install_btn.config(state=tk.NORMAL)
            messagebox.showerror("Error", f"Installation error: {str(e)}")
    
    def download_with_progress(self, url, dest, label):
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "ArchAssistant-Installer/2.0"
            })
            
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
                            if total > 1024 * 1024 * 1024:
                                gb = downloaded / (1024 * 1024 * 1024)
                                total_gb = total / (1024 * 1024 * 1024)
                                pct_label = f"{gb:.2f} / {total_gb:.2f} GB"
                            else:
                                mb = downloaded / (1024 * 1024)
                                total_mb = total / (1024 * 1024)
                                pct_label = f"{mb:.1f} / {total_mb:.1f} MB"
                            
                            self.update_progress(pct, f"{label}: {pct_label} ({pct}%)")
                return True
        except Exception as e:
            print(f"Download error: {e}")
            return False
    
    def extract_and_install(self, app_zip, models_zip, install_dir, is_windows):
        import zipfile
        
        # Create install directory
        if os.path.exists(install_dir):
            shutil.rmtree(install_dir)
        os.makedirs(install_dir, exist_ok=True)
        
        # Extract app
        with zipfile.ZipFile(app_zip, 'r') as zf:
            zf.extractall(tempfile.gettempdir() + "/arch-app-extract")
        
        # Find the app directory in the zip
        extract_dir = tempfile.gettempdir() + "/arch-app-extract"
        if os.path.exists(os.path.join(extract_dir, "Arch Assistant")):
            source = os.path.join(extract_dir, "Arch Assistant")
        elif os.path.exists(os.path.join(extract_dir)):
            source = extract_dir
        else:
            source = extract_dir
        
        # Copy app files
        for item in os.listdir(source):
            s = os.path.join(source, item)
            d = os.path.join(install_dir, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
        
        # Clean up temp
        shutil.rmtree(extract_dir, ignore_errors=True)
        if os.path.exists(app_zip):
            os.remove(app_zip)
        
        # Extract models
        if models_zip and os.path.exists(models_zip):
            models_dir = os.path.join(install_dir, "ollama", "models")
            os.makedirs(models_dir, exist_ok=True)
            with zipfile.ZipFile(models_zip, 'r') as zf:
                zf.extractall(models_dir)
            os.remove(models_zip)
    
    def create_shortcuts(self, install_dir, is_windows):
        import stat
        
        if is_windows:
            # Create desktop shortcut via PowerShell
            ps_script = (
                f'$ws = New-Object -ComObject WScript.Shell; '
                f'$desktop = [Environment]::GetFolderPath("Desktop"); '
                f'$sc = $ws.CreateShortcut($desktop + "\\Arch Assistant.lnk"); '
                f'$sc.TargetPath = "{install_dir}\\Arch.exe"; '
                f'$sc.WorkingDirectory = "{install_dir}"; '
                f'$sc.Description = "Arch AI Assistant"; '
                f'$sc.Save()'
            )
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
    
    def show_done_message(self):
        messagebox.showinfo(
            "Installation Complete",
            f"Arch Assistant has been installed to:\n{self.install_path.get()}\n\n"
            "Desktop shortcut created. Double-click to launch.\n\n"
            "Total installed size: ~5.5 GB (app + AI models)"
        )
        self.root.quit()


if __name__ == "__main__":
    import platform
    import shutil
    
    root = tk.Tk()
    app = InstallerApp(root)
    root.mainloop()
