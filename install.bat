@echo off
setlocal
title Arch Assistant Installer
color 0F

echo.
echo  ============================================================
echo              ARCH ASSISTANT INSTALLER
echo  ============================================================
echo.
echo  This will download and install Arch Assistant to:
echo    C:\Program Files\Arch Assistant
echo.
echo  Requirements:
echo    - Internet connection
echo    - ~300 MB free disk space
echo    - Python 3.10+ (for AI features)
echo.
echo  ============================================================
echo.

choice /C YN /M "Proceed with installation"
if errorlevel 2 goto :cancelled

set "REPO_URL=https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/Arch-Assistant-App.zip"
set "INSTALL_DIR=C:\Program Files\Arch Assistant"
set "TEMP_DIR=%TEMP%\arch-assistant-setup"

echo.
echo [1/4] Downloading from GitHub...
echo.

if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%" 2>nul
mkdir "%TEMP_DIR%" 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
  "$url = '%REPO_URL%'; " ^
  "$out = '%TEMP_DIR%\Arch-Assistant-App.zip'; " ^
  "Write-Host 'Connecting to GitHub...'; " ^
  "try { " ^
  "  $wc = New-Object System.Net.WebClient; " ^
  "  $wc.Headers.Add('User-Agent', 'ArchAssistant-Installer/1.0'); " ^
  "  $wc.DownloadFile($url, $out); " ^
  "  $size = (Get-Item $out).Length; " ^
  "  Write-Host ('Downloaded: ' + [math]::Round($size/1MB,1) + ' MB'); " ^
  "} catch { " ^
  "  Write-Host ('ERROR: ' + $_.Exception.Message); " ^
  "  exit 1; " ^
  "}"

if errorlevel 1 (
    echo.
    echo  ERROR: Download failed. Check your internet connection.
    echo.
    pause
    goto :cleanup
)

echo.
echo [2/4] Extracting files...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Add-Type -Assembly System.IO.Compression.FileSystem; " ^
  "$zip = '%TEMP_DIR%\Arch-Assistant-App.zip'; " ^
  "$extract = '%TEMP_DIR%\app'; " ^
  "if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }; " ^
  "[System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $extract); " ^
  "if (-not (Test-Path '$TEMP_DIR%\app\Arch Assistant')) { " ^
  "  Write-Host 'ERROR: Archive does not contain Arch Assistant folder'; " ^
  "  exit 1; " ^
  "} " ^
  "Write-Host 'Extraction complete.'"

if errorlevel 1 (
    echo.
    echo  ERROR: Archive is corrupted or missing files.
    echo  Try downloading again.
    echo.
    pause
    goto :cleanup
)

echo.
echo [3/4] Installing to %INSTALL_DIR%...
echo.

if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%" 2>nul
mkdir "%INSTALL_DIR%" 2>nul

robocopy "%TEMP_DIR%\app\Arch Assistant" "%INSTALL_DIR%" /E /NFL /NDL /NJH /NJS /NC /NS
if errorlevel 8 (
    echo.
    echo  ERROR: Could not write to %INSTALL_DIR%
    echo  Right-click this file and select "Run as administrator"
    echo.
    pause
    goto :cleanup
)

echo.
echo [4/4] Creating shortcuts...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$desktop = [Environment]::GetFolderPath('Desktop'); " ^
  "$sm = $ws.SpecialFolders.Item('Programs') + '\Arch Assistant'; " ^
  "New-Item -ItemType Directory -Path $sm -Force | Out-Null; " ^
  "$sc = $ws.CreateShortcut($desktop + '\Arch Assistant.lnk'); " ^
  "$sc.TargetPath = '%INSTALL_DIR%\Arch.exe'; " ^
  "$sc.WorkingDirectory = '%INSTALL_DIR%'; " ^
  "$sc.Description = 'Arch AI Assistant'; " ^
  "$sc.Save(); " ^
  "$sc2 = $ws.CreateShortcut($sm + '\Arch Assistant.lnk'); " ^
  "$sc2.TargetPath = '%INSTALL_DIR%\Arch.exe'; " ^
  "$sc2.WorkingDirectory = '%INSTALL_DIR%'; " ^
  "$sc2.Description = 'Arch AI Assistant'; " ^
  "$sc2.Save(); " ^
  "Write-Host 'Shortcuts created.'"

echo.
echo  ============================================================
echo            INSTALLATION COMPLETE
echo  ============================================================
echo.
echo  Installed to: %INSTALL_DIR%
echo  Desktop shortcut created.
echo.
echo  First launch will download AI models (~2 GB) automatically.
echo.

choice /C YN /M "Launch Arch Assistant now"
if errorlevel 2 goto :cleanup

start "" "%INSTALL_DIR%\Arch.exe"

:cleanup
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%" 2>nul
echo.
echo  Installer finished.
timeout /t 3 >nul
exit /b 0

:cancelled
echo.
echo  Installation cancelled.
timeout /t 2 >nul
exit /b 0
