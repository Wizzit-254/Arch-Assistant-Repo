@echo off
setlocal
title Arch Assistant Installer
mode con: cols=70 lines=30
color 0F

echo.
echo  ============================================================
echo              ARCH ASSISTANT INSTALLER
echo  ============================================================
echo.
echo   This will download and install Arch Assistant to:
echo     C:\Program Files\Arch Assistant
echo.
echo   Requirements:
echo     - Internet connection
echo     - ~300 MB free disk space
echo     - Python 3.10+ (for AI features)
echo.
echo  ============================================================
echo.

choice /C YN /M "  Proceed with installation? [Y/N]"
if errorlevel 2 goto :cancelled

echo.
echo  [1/4] Connecting to GitHub...
echo.

set "REPO_URL=https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/Arch-Assistant-App.zip"
set "INSTALL_DIR=C:\Program Files\Arch Assistant"
set "TEMP_DIR=%TEMP%\arch-assistant-setup"

if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%" 2>nul
mkdir "%TEMP_DIR%" 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop'; " ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
  "$url = '%REPO_URL%'; " ^
  "$out = '%TEMP_DIR%\Arch-Assistant-App.zip'; " ^
  "Write-Host '  Connecting to GitHub...'; " ^
  "Write-Host ''; " ^
  "try { " ^
  "  $req = [System.Net.HttpWebRequest]::Create($url); " ^
  "  $req.UserAgent = 'ArchAssistant-Installer/1.0'; " ^
  "  $req.AllowAutoRedirect = $true; " ^
  "  $resp = $req.GetResponse(); " ^
  "  $total = $resp.ContentLength; " ^
  "  $rs = $resp.GetResponseStream(); " ^
  "  $fs = [System.IO.File]::Create($out); " ^
  "  $buf = New-Object byte[] 65536; " ^
  "  $got = 0; " ^
  "  $lastPct = -1; " ^
  "  while (($n = $rs.Read($buf, 0, $buf.Length)) -gt 0) { " ^
  "    $fs.Write($buf, 0, $n); " ^
  "    $got += $n; " ^
  "    if ($total -gt 0) { " ^
  "      $pct = [math]::Floor($got / $total * 100); " ^
  "      if ($pct -ne $lastPct) { " ^
  "        $mb = [math]::Round($got / 1MB, 1); " ^
  "        $totalMb = [math]::Round($total / 1MB, 1); " ^
  "        $bar = '[' + ('#' * [math]::Min($pct, 100)) + ('-' * [math]::Max(100 - $pct, 0)) + ']'; " ^
  "        Write-Host ('`r  Downloading: ' + $bar + ' ' + $pct + '%% (' + $mb + ' / ' + $totalMb + ' MB)') -NoNewline; " ^
  "        $lastPct = $pct; " ^
  "      } " ^
  "    } else { " ^
  "      $mb = [math]::Round($got / 1MB, 1); " ^
  "      Write-Host ('`r  Downloading: ' + $mb + ' MB') -NoNewline; " ^
  "    } " ^
  "  } " ^
  "  $fs.Close(); $rs.Close(); $resp.Close(); " ^
  "  Write-Host ''; " ^
  "  Write-Host ''; " ^
  "  Write-Host ('  Downloaded: ' + [math]::Round((Get-Item $out).Length / 1MB, 1) + ' MB'); " ^
  "} catch { " ^
  "  Write-Host ''; " ^
  "  Write-Host ('  ERROR: ' + $_.Exception.Message); " ^
  "  exit 1; " ^
  "}"

if errorlevel 1 (
    echo.
    echo  ----------------------------------------------------------
    echo   Download failed. Check your internet connection.
    echo  ----------------------------------------------------------
    echo.
    pause
    goto :cleanup
)

echo.
echo  [2/4] Extracting files...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Add-Type -Assembly System.IO.Compression.FileSystem; " ^
  "$zip = '%TEMP_DIR%\Arch-Assistant-App.zip'; " ^
  "$extract = '%TEMP_DIR%\app'; " ^
  "if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }; " ^
  "Write-Host '  Extracting...'; " ^
  "[System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $extract); " ^
  "if (-not (Test-Path '%TEMP_DIR%\app\Arch Assistant')) { " ^
  "  Write-Host '  ERROR: Archive missing Arch Assistant folder'; " ^
  "  exit 1; " ^
  "} " ^
  "Write-Host '  Extraction complete.'"

if errorlevel 1 (
    echo.
    echo  ----------------------------------------------------------
    echo   Archive is corrupted. Try downloading again.
    echo  ----------------------------------------------------------
    echo.
    pause
    goto :cleanup
)

echo.
echo  [3/4] Installing to %INSTALL_DIR%...
echo.

if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%" 2>nul
mkdir "%INSTALL_DIR%" 2>nul

robocopy "%TEMP_DIR%\app\Arch Assistant" "%INSTALL_DIR%" /E /NFL /NDL /NJH /NJS /NC /NS >nul 2>&1
if errorlevel 8 (
    echo  ----------------------------------------------------------
    echo   Could not write to %INSTALL_DIR%
    echo   Right-click install.bat and "Run as administrator"
    echo  ----------------------------------------------------------
    echo.
    pause
    goto :cleanup
)
echo  Install complete.

echo.
echo  [4/4] Creating shortcuts...
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
  "Write-Host '  Shortcuts created.'"

echo.
echo  ============================================================
echo            INSTALLATION COMPLETE
echo  ============================================================
echo.
echo   Installed to: %INSTALL_DIR%
echo   Desktop shortcut created.
echo.
echo   First launch will download AI models (~2 GB) automatically.
echo.

choice /C YN /M "  Launch Arch Assistant now? [Y/N]"
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
