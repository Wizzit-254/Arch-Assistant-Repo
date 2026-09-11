#!/usr/bin/env python3
"""
Persistent Tunnel Manager for Arch Assistant
Manages both localtunnel and cloudflared as fallback options.
Auto-restarts the tunnel if it fails.
"""

import subprocess
import time
import os
import re
import sys
import socket
import urllib.request
import urllib.parse

CLOUDFLARED_PATH = r"C:\Users/trevo/tmp/cloudflared.exe"
NGROK_PATH = r"C:\Users/trevo/tmp/ngrok.exe"
LOCALTUNNEL_PORT = 8090
URL_FILE = r"C:\Users/trevo/tmp\tunnel-url.txt"
LOG_FILE = r"C:\Users/trevo/tmp\tunnel-manager.log"

def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)

def check_server():
    """Check if the web server is running."""
    try:
        resp = urllib.request.urlopen(f'http://127.0.0.1:{LOCALTUNNEL_PORT}/', timeout=5)
        return resp.status == 200
    except:
        return False

def start_cloudflared():
    """Start cloudflared tunnel and return the URL."""
    log("Starting Cloudflare Tunnel...")
    proc = subprocess.Popen(
        [CLOUDFLARED_PATH, "tunnel", "--url", f"http://127.0.0.1:{LOCALTUNNEL_PORT}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        universal_newlines=True,
        bufsize=1
    )
    
    url = None
    start_time = time.time()
    
    while time.time() - start_time < 30:
        line = proc.stdout.readline()
        if not line:
            time.sleep(1)
            if not check_server():
                log("Server died, restarting...")
                restart_server()
            continue
        
        line = line.strip()
        log(f"[cloudflared] {line}")
        
        # Extract URL
        match = re.search(r'(https://[a-z0-9-]+\.trycloudflare\.com)', line)
        if match:
            url = match.group(1)
            with open(URL_FILE, "w") as f:
                f.write(url)
            log(f"Tunnel URL: {url}")
            return proc, url
    
    return proc, None

def restart_server():
    """Restart the Node.js web server."""
    log("Restarting web server...")
    
    # Kill existing node processes
    subprocess.run(['taskkill', '/IM', 'node.exe', '/F'], capture_output=True)
    subprocess.run(['taskkill', '/IM', 'powershell.exe', '/F'], capture_output=True)
    time.sleep(3)
    
    # Set environment variables
    env = os.environ.copy()
    env['PORT'] = str(LOCALTUNNEL_PORT)
    env['TRUST_PROXY'] = '1'
    
    # Generate ARCH_SECRET if not set
    secret_file = os.path.join(os.environ.get('APPDATA', ''), 'arch-secret')
    if os.path.exists(secret_file):
        with open(secret_file) as f:
            env['ARCH_SECRET'] = f.read().strip()
    else:
        env['ARCH_SECRET'] = os.urandom(32).hex()
    
    # Start server
    subprocess.Popen(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
         r'C:\Users/trevo/Downloads\WEBSITE\start-arch.ps1'],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )
    
    time.sleep(8)
    
    # Verify server is up
    if not check_server():
        log("ERROR: Server failed to start!")
        # Try starting node directly
        subprocess.Popen(
            ['node', 'server.mjs'],
            cwd=r'C:\Users/trevo/Downloads\WEBSITE',
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(5)

def main():
    log("=== Arch Assistant Tunnel Manager ===")
    
    # Ensure server is running
    if not check_server():
        restart_server()
    
    if not check_server():
        log("FATAL: Cannot start web server!")
        sys.exit(1)
    
    log("Web server is running")
    
    while True:
        proc, url = start_cloudflared()
        
        if url:
            log(f"Tunnel active at: {url}")
            
            # Monitor the tunnel
            while True:
                # Check if tunnel process is still running
                if proc.poll() is not None:
                    log("Tunnel process exited, restarting...")
                    break
                
                # Check if server is still running
                if not check_server():
                    log("Server not responding, restarting...")
                    restart_server()
                
                time.sleep(30)
            
            # Kill old process
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except:
                proc.kill()
        else:
            log("Failed to get tunnel URL, retrying in 10 seconds...")
        
        time.sleep(10)

if __name__ == "__main__":
    main()
