@echo off
setlocal EnableExtensions
title Arch Assistant - Tiny Downloader
color 0A

set "STAGE2_URL=https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/ArchAssistant-Stage2.exe"
set "TEMP_DIR=%LOCALAPPDATA%\Temp\arch-assistant-stage1"
set "OUTPUT_EXE=%TEMP_DIR%\ArchAssistant-Stage2.exe"

if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%" 2>nul
mkdir "%TEMP_DIR%" 2>nul

echo.
echo  Arch Assistant Installer - Bootstrap (Stage 1)
echo  Downloading full installer (~50 MB)...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop'; " ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
  "$url = '%STAGE2_URL%'; " ^
  "$out = '%OUTPUT_EXE%'; " ^
  "$req = [System.Net.HttpWebRequest]::Create($url); " ^
  "$req.UserAgent = 'ArchAssistant-Bootstrap/1.0'; " ^
  "$req.AllowAutoRedirect = $true; " ^
  "$req.Timeout = 600000; " ^
  "$req.ReadWriteTimeout = 600000; " ^
  "$resp = $req.GetResponse(); " ^
  "$total = $resp.ContentLength; " ^
  "$rs = $resp.GetResponseStream(); " ^
  "$fs = [System.IO.File]::Create($out); " ^
  "$buf = New-Object byte[] 65536; " ^
  "$got = 0; $lastPct = -1; " ^
  "while (($n = $rs.Read($buf, 0, $buf.Length)) -gt 0) { " ^
  "  $fs.Write($buf, 0, $n); " ^
  "  $got += $n; " ^
  "  if ($total -gt 0) { " ^
  "    $pct = [math]::Floor($got / $total * 100); " ^
  "    if ($pct -ne $lastPct) { " ^
  "      $mb = [math]::Round($got / 1MB, 1); " ^
  "      $totalMb = [math]::Round($total / 1MB, 1); " ^
  "      Write-Host ('  Downloading: ' + $pct + '% (' + $mb + ' / ' + $totalMb + ' MB)') -NoNewline; " ^
  "      $lastPct = $pct; " ^
  "    } " ^
  "  } " ^
  "} " ^
  "$fs.Close(); $rs.Close(); $resp.Close(); " ^
  "Write-Host '';"

if errorlevel 1 (
    echo.
    echo  Download failed. Please check your internet connection.
    echo  Or download manually from:
    echo  https://github.com/Wizzit-254/Arch-Assistant-Repo/releases
    echo.
    pause
    exit /b 1
)

echo.
echo  Launching full installer...
Start "" "%OUTPUT_EXE%"

if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%" 2>nul
exit /b 0
