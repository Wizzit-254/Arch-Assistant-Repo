"""
Arch Assistant - Release Packager
Creates a GitHub release with the full app archive.

Usage:
  1. pip install PyGithub (or use gh CLI)
  2. python create_release.py --token YOUR_GITHUB_TOKEN --tag v1.0.0

This script:
  - Zips the full Arch Assistant (Electron + Python + Ollama + models)
  - Creates a GitHub release
  - Uploads the archive as a release asset
"""
import os
import sys
import shutil
import zipfile
import argparse
import subprocess
import json
import urllib.request
import urllib.error

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Arch Assistant")
RELEASE_NAME = "Arch-Assistant-App.zip"


def find_app_dir():
    """Find the Arch Assistant directory with all files."""
    candidates = [
        APP_DIR,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Arch Assistant"),
        os.environ.get("ARCH_SOURCE_DIR", ""),
    ]
    for c in candidates:
        if c and os.path.isdir(os.path.join(c, "api_server.py")):
            return c
    print("ERROR: Cannot find Arch Assistant directory with api_server.py")
    print("Set ARCH_SOURCE_DIR environment variable to the full app path.")
    sys.exit(1)


def create_archive(source_dir, output_path):
    """Create a ZIP archive of the full app."""
    print(f"Creating archive from: {source_dir}")
    skip_dirs = {"__pycache__", ".git", "node_modules", "arch-assistant"}
    total = 0
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(source_dir):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for f in files:
                fp = os.path.join(root, f)
                arcname = os.path.join("Arch Assistant", os.path.relpath(fp, source_dir))
                zf.write(fp, arcname)
                total += 1
                if total % 100 == 0:
                    print(f"  Packed {total} files...")
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"Archive created: {output_path} ({size_mb:.1f} MB, {total} files)")
    return output_path


def create_github_release(owner, repo, tag, token, archive_path):
    """Create a GitHub release and upload the archive."""
    import base64

    api = f"https://api.github.com/repos/{owner}/{repo}/releases"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Create release
    data = json.dumps({
        "tag_name": tag,
        "name": f"Arch Assistant {tag}",
        "body": f"Arch Assistant {tag} - Full application archive.\n\n"
                f"Download `Arch-Assistant-App.zip`, extract, and run `ArchAssistant-Installer.exe`.",
        "draft": False,
        "prerelease": False,
    }).encode("utf-8")

    req = urllib.request.Request(api, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            release = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Failed to create release: {e.code} {e.read().decode()}")
        sys.exit(1)

    upload_url = release["upload_url"].replace("{?name,label}", f"?name={RELEASE_NAME}")
    print(f"Release created: {release['html_url']}")

    # Upload asset
    print("Uploading archive...")
    with open(archive_path, "rb") as f:
        asset_data = f.read()

    req2 = urllib.request.Request(
        upload_url,
        data=asset_data,
        headers={
            "Authorization": f"token {token}",
            "Content-Type": "application/zip",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req2) as resp:
            asset = json.loads(resp.read().decode())
        print(f"Uploaded: {asset['browser_download_url']}")
        return asset["browser_download_url"]
    except urllib.error.HTTPError as e:
        print(f"Upload failed: {e.code} {e.read().decode()}")
        sys.exit(1)


def update_installer_url(owner, repo):
    """Update installer.cs with the correct GitHub URL."""
    cs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "installer.cs")
    if not os.path.exists(cs_path):
        print("Warning: installer.cs not found, skipping URL update")
        return
    with open(cs_path, "r") as f:
        content = f.read()
    content = content.replace("YOUR_GITHUB_USERNAME", owner)
    content = content.replace('static string RepoName = "Arch-Assistant-Repo"',
                              f'static string RepoName = "{repo}"')
    with open(cs_path, "w") as f:
        f.write(content)
    print(f"Updated installer.cs with owner={owner}, repo={repo}")

    # Recompile
    csc = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    exe_path = cs_path.replace(".cs", ".exe")
    refs = [
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.Windows.Forms.dll",
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.Drawing.dll",
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.IO.Compression.dll",
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.IO.Compression.FileSystem.dll",
    ]
    ref_args = [f"/reference:{r}" for r in refs]
    cmd = [csc, "/target:winexe", f"/out:{exe_path}"] + ref_args + [cs_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Recompiled: {exe_path} ({os.path.getsize(exe_path) / 1024:.1f} KB)")
    else:
        print(f"Recompile failed: {result.stderr}")


def main():
    parser = argparse.ArgumentParser(description="Create Arch Assistant GitHub release")
    parser.add_argument("--token", required=True, help="GitHub personal access token")
    parser.add_argument("--owner", default="YOUR_GITHUB_USERNAME", help="GitHub username/org")
    parser.add_argument("--repo", default="Arch-Assistant-Repo", help="Repository name")
    parser.add_argument("--tag", default="v1.0.0", help="Release tag")
    parser.add_argument("--source", help="Path to full Arch Assistant directory")
    parser.add_argument("--upload-only", action="store_true", help="Skip archive creation")
    args = parser.parse_args()

    source_dir = args.source or find_app_dir()

    # Step 1: Create archive
    archive_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), RELEASE_NAME)
    if not args.upload_only:
        create_archive(source_dir, archive_path)

    # Step 2: Update installer with correct URL
    update_installer_url(args.owner, args.repo)

    # Step 3: Create GitHub release and upload
    create_github_release(args.owner, args.repo, args.tag, args.token, archive_path)

    print("\nDone! Users can now:")
    print(f"1. Download ArchAssistant-Installer.exe from your repo")
    print(f"2. Run it — it downloads the full app from the release")
    print(f"3. First launch downloads AI models automatically")


if __name__ == "__main__":
    main()
