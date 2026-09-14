# Sanitize an Arch Assistant folder before sharing it (E: master, zips, etc).
# Removes personal data so a fresh PC starts clean, then resets identity.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File sanitize-dist.ps1 "<folder>"
param([Parameter(Mandatory = $true)][string]$Dir)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path (Join-Path $Dir 'api_server.py'))) { throw "Not an Arch app folder: $Dir" }

# 1. Chats + first-run markers + logs + bytecode (personal / machine-specific)
Remove-Item (Join-Path $Dir 'chats.json') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Dir 'arch.intro.seen') -Force -ErrorAction SilentlyContinue
Get-ChildItem $Dir -Filter '*.log' | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem $Dir -Directory -Filter '__pycache__' -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# 2. Identity reset (name, key, persona). Voices + pacing + models stay.
$cfgPath = Join-Path $Dir 'Config.json'
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
$cfg.profile.name = 'User'
$cfg.profile.nickname = 'User'
$cfg.profile.language = 'en'
$cfg.profile.theme = 'dark'
$cfg.profile.voice = 'Angel'
$cfg.profile.persona = ''
$cfg.fish_api_key = ''
$cfg | ConvertTo-Json -Depth 6 | Set-Content $cfgPath -Encoding UTF8

Write-Output "Sanitized: $Dir (chats/logs/markers gone, identity reset, fish key blanked)"
