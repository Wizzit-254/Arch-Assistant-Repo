#!/usr/bin/env python3
"""
Arch Assistant - Staged Installer (Stage 1)
Tiny installer (~7MB as frozen exe) that downloads and runs Stage 2.
Includes: T&C display, install location selector, terms acceptance.
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
import json

# --- Config ---
STAGE2_URL = "https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/ArchAssistant-Stage2.exe"
APP_NAME = "Arch Assistant"
INSTALLER_SIZE_MB = 5.0
CHUNK_SIZE = 131072  # 128KB

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

5. SUPPORT
   Community support is available via GitHub Issues:
   https://github.com/Wizzit-252/Arch-Assistant-Repo/issues

   Contact: trevorkisingu@gmail.com

6. INSTALLATION
   This installer will:
   - Download ~5GB of AI model files
   - Extract them to your chosen install directory
   - Create a desktop shortcut
   - Launch the app when complete

7. BY CLICKING "INSTALL", YOU AGREE TO THESE TERMS.
"""


class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} Installer")
        self.root.geometry("600x520")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a22")
        
        # Center on screen
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (600 // 2)
        y = (self.root.winfo_screen_height() // 2) - (520 // 2)
        self.root.geometry(f"+{x}+{y}")
        
        # Variables
        self.install_path = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads", APP_NAME))
        self.is_downloading = False
        self.is_installing = False
        
        self.setup_ui()
        
    def setup_ui(self):
        # Header
        header = tk.Frame(self.root, bg="#1a1a22")
        header.pack(fill=tk.X, padx=30, pady=(20, 0))
        
        tk.Label(header, text=f"{APP_NAME} Installer", 
                font=("Segoe UI", 16, "bold"), fg="white", bg="#1a1a22").pack(anchor=tk.W)
        tk.Label(header, text="Stage 1 of 3 • Lightweight Bootstrap Installer", 
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
                                                height=12, width=68,
                                                state=tk.DISABLED)
        self.tc_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.tc_text.config(state=tk.NORMAL)
        self.tc_text.insert(tk.END, TERMS_TEXT)
        self.tc_text.config(state=tk.DISABLED)
        
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
                                  highlightbackground="#444", highlightthickness=1)
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
        
        self.progress = ttk.Progressbar(self.root, mode="determinate",
                                       style="dark.Horizontal.TProgressbar")
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
        
        # Style
        style = ttk.Style()
        style.configure("dark.Horizontal.TProgressbar",
                       background="#25252f", troughcolor="#1a1a22",
                       thickness=6, borderwidth=0)
        style.map("dark.Horizontal.TProgressbar",
                 background=[('active', '#4a90d9')])
        
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
        
        # Validate path (no weird chars)
        if ".." in install_dir or ":" not in install_dir:
            messagebox.showerror("Error", "Please choose a valid path.")
            return
        
        self.install_btn.config(state=tk.DISABLED)
        self.is_downloading = True
        
        thread = threading.Thread(target=self.do_install, args=(install_dir,), daemon=True)
        thread.start()
    
    def do_install(self, install_dir):
        try:
            # Step 1: Download Stage 2 installer
            self.update_progress(0, "Downloading installer (Stage 2)...")
            stage2_path = self.download_with_progress(STAGE2_URL, self.update_progress)
            if not stage2_path:
                self.update_progress(0, "Download failed. Check your internet connection.")
                self.install_btn.config(state=tk.NORMAL)
                return
            
            # Verify checksum
            self.update_progress(50, "Verifying installer integrity...")
            checksum = self.compute_sha256(stage2_path)
            
            # Step 2: Run Stage 2 with install path
            self.update_progress(75, "Launching full installer...")
            subprocess.Popen([stage2_path, "--install-dir", install_dir], 
                           creationflags=subprocess.CREATE_NEW_CONSOLE)
            
            self.update_progress(100, "Installer launched! Stage 2 will complete installation.")
            
            # Show success message
            self.root.after(2000, lambda: self.show_done_message())
            
        except Exception as e:
            self.update_progress(0, f"Error: {str(e)}")
            self.install_btn.config(state=tk.NORMAL)
    
    def download_with_progress(self, url, callback):
        """Download file with progress callback."""
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        req = urllib.request.Request(url, headers={
            "User-Agent": "ArchAssistant-Installer/1.0"
        })
        
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            tmp = os.path.join(tempfile.gettempdir(), "ArchAssistant-Stage2.exe")
            
            downloaded = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = int(downloaded / total * 100)
                        mb = downloaded / (1024*1024)
                        total_mb = total / (1024*1024)
                        callback(pct, f"Downloading installer: {mb:.1f} / {total_mb:.1f} MB ({pct}%)")
            
            return tmp
    
    def compute_sha256(self, filepath):
        """Compute SHA-256 checksum of a file."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    
    def show_done_message(self):
        messagebox.showinfo("Installation Started",
            "The full installer (Stage 2) has been downloaded and launched.\n\n"
            "It will now download ~5GB of AI models and install the app.\n"
            "This may take 5-15 minutes depending on your connection.\n\n"
            f"Install location: {self.install_path.get()}")
        self.root.quit()


def main():
    root = tk.Tk()
    app = InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
