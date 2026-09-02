@echo off
setlocal
title Arch Assistant - Hardware Compatibility Check
color 0F

echo.
echo  ============================================================
echo            ARCH ASSISTANT - SYSTEM CHECK
echo  ============================================================
echo.

echo  [1/4] Checking CPU...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1; " ^
  "Write-Host ('  CPU: ' + $cpu.Name); " ^
  "Write-Host ('  Cores: ' + $cpu.NumberOfCores + ' | Threads: ' + $cpu.NumberOfLogicalProcessors); " ^
  "$ram = [math]::Round((Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum / 1GB, 1); " ^
  "Write-Host ('  RAM: ' + $ram + ' GB'); " ^
  "if ($ram -lt 4) { Write-Host '  WARNING: Less than 4 GB RAM. AI response will be very slow.'; } " ^
  "if ($ram -ge 8) { Write-Host '  OK: 8+ GB RAM recommended for smooth AI operation.'; }"

if errorlevel 1 (
    echo  Could not check CPU/RAM automatically.
)

echo.
echo [2/4] Checking disk space...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$drive = Get-Item '%USERPROFILE%\Downloads\Arch Assistant' | Select-Object -ExpandProperty PSDrive -ErrorAction SilentlyContinue; " ^
  "if (-not $drive) { $drive = Get-PSDrive C; } " ^
  "$free = [math]::Round($drive.Used / 1GB, 1); " ^
  "$total = [math]::Round($drive.Used / 1GB + $drive.Free / 1GB, 1); " ^
  "$freeSpace = [math]::Round($drive.Free / 1GB, 1); " ^
  "Write-Host ('  Drive ' + $drive.Name + ': ' + $freeSpace + ' GB free of ' + $total + ' GB'); " ^
  "if ($freeSpace -lt 1) { Write-Host '  ERROR: Need at least 1 GB free space.'; exit 1; } " ^
  "if ($freeSpace -lt 3) { Write-Host '  WARNING: Less than 3 GB free. Models require ~2 GB.'; }"

if errorlevel 1 (
    echo.
    echo  ----------------------------------------------------------
    echo   Not enough disk space. Free up space and try again.
    echo  ----------------------------------------------------------
    echo.
    pause
    exit /b 1
)

echo.
echo [3/4] Checking Python...
echo.

set "PY_FOUND=0"
py -3 --version >nul 2>nul && (echo   Found Python 3 && set "PY_FOUND=1")
if not "!PY_FOUND!"=="1" (
    python --version >nul 2>nul && (echo   Found Python && set "PY_FOUND=1")
)
if not "!PY_FOUND!"=="1" (
    echo   Python 3.10+ not found.
    echo   The installer will attempt to install it via winget.
)

echo.
echo [4/4] Checking network...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop'; " ^
  "try { " ^
  "  $req = [System.Net.HttpWebRequest]::Create('https://github.com'); " ^
  "  $req.Timeout = 5000; " ^
  "  $resp = $req.GetResponse(); " ^
  "  Write-Host ('  Network OK: HTTP ' + $resp.StatusCode); " ^
  "  $resp.Close(); " ^
  "} catch { " ^
  "  Write-Host ('  ERROR: Cannot reach GitHub - ' + $_.Exception.Message); " ^
  "  exit 1; " ^
  "}"

if errorlevel 1 (
    echo.
    echo  ----------------------------------------------------------
    echo   Network check failed. Cannot reach GitHub.
    echo   Please check your internet connection.
    echo  ----------------------------------------------------------
    echo.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo            SYSTEM CHECK PASSED
echo  ============================================================
echo.
echo   Your system is ready for Arch Assistant.
echo.

pause
exit /b 0
