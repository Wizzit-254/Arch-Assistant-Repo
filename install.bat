@echo off
setlocal EnableExtensions
title Arch Assistant Installer
color 0F

echo.
echo  ============================================================
echo              ARCH ASSISTANT INSTALLER
echo  ============================================================
echo.
set "INSTALL_DIR=%USERPROFILE%\Downloads\Arch Assistant"
echo   This will install Arch Assistant to:
echo     %INSTALL_DIR%
echo.
echo   No administrator rights required.
echo.
echo  ============================================================
echo.

choice /C YN /M "  Run system check first? [Y/N]"
if errorlevel 2 goto :skip_check

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1; " ^
  "Write-Host ('  CPU: ' + $cpu.Name); " ^
  "Write-Host ('  Cores: ' + $cpu.NumberOfCores + ' | Threads: ' + $cpu.NumberOfLogicalProcessors); " ^
  "$ram = [math]::Round((Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum / 1GB, 1); " ^
  "Write-Host ('  RAM: ' + $ram + ' GB'); " ^
  "if ($ram -ge 8) { Write-Host '  OK: 8+ GB RAM for smooth AI operation.'; } else { Write-Host '  WARNING: Less than 8 GB RAM. AI will be slower.'; }"
echo.
echo.

:skip_check
choice /C YN /M "  Proceed with installation? [Y/N]"
if errorlevel 2 goto :cancelled

set "REPO_URL=https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/Arch-Assistant-App.zip"
set "TEMP_DIR=%LOCALAPPDATA%\Temp\arch-assistant-setup"

if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%" 2>nul
mkdir "%TEMP_DIR%" 2>nul

echo.
echo [1/4] Checking Python...
echo.

REM Check Python availability
set "PY_CMD="
for %%P in (py python python3) do (
    where %%P >nul 2>nul && (
        for /f "tokens=*" %%V in ('%%P -3 --version 2^>nul') do (
            echo   Found: %%V
            set "PY_CMD=%%P"
            goto :python_done
        )
    )
)
:python_done

if not defined PY_CMD (
    echo  Python 3.10+ is required but not found.
    echo  Installing Python silently via winget...
    echo.
    
    winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        winget install Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
        if errorlevel 1 (
            echo.
            echo  ----------------------------------------------------------
            echo   Could not install Python automatically.
            echo   Please install Python 3.10+ from:
            echo   https://python.org/downloads/
            echo  ----------------------------------------------------------
            echo.
            pause
            goto :cleanup
        )
    )
    echo  Python installed. Waiting for PATH to update...
    timeout /t 10 >nul
    set "PY_CMD="
    for %%P in (py python python3) do (
        where %%P >nul 2>nul && set "PY_CMD=%%P" && goto :check_py2
    )
    :check_py2
    if not defined PY_CMD (
        echo  Python install succeeded but not on PATH. Restart this installer after reboot.
        pause
        goto :cleanup
    )
    for /f "tokens=*" %%V in ('py -3 --version 2^>nul') do echo   Found: %%V
)

echo.
echo [2/4] Downloading Arch Assistant...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop'; " ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
  "$url = '%REPO_URL%'; " ^
  "$out = '%TEMP_DIR%\Arch-Assistant-App.zip'; " ^
  "Write-Host '  Connecting to GitHub...'; " ^
  "$req = [System.Net.HttpWebRequest]::Create($url); " ^
  "$req.UserAgent = 'ArchAssistant-Installer/1.0'; " ^
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
  "      $filled = [math]::Min($pct, 100); " ^
  "      $empty = [math]::Max(100 - $pct, 0); " ^
  "      $bar = '[' + ('#' * $filled) + ('-' * $empty) + ']'; " ^
  "      Write-Host ('.r  Downloading: ' + $bar + ' ' + $pct + '% (' + $mb + ' / ' + $totalMb + ' MB)') -NoNewline; " ^
  "      $lastPct = $pct; " ^
  "    } " ^
  "  } " ^
  "} " ^
  "$fs.Close(); $rs.Close(); $resp.Close(); " ^
  "Write-Host ''; Write-Host ''; " ^
  "Write-Host ('  Done: ' + [math]::Round((Get-Item $out).Length / 1MB, 1) + ' MB');"

if errorlevel 1 (
    echo.
    echo  -----------------------------------------------
    echo   Download failed. Check your internet.
    echo  -----------------------------------------------
    echo.
    pause
    goto :cleanup
)

echo.
echo [3/4] Extracting files...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Add-Type -Assembly System.IO.Compression.FileSystem; " ^
  "$zip = '%TEMP_DIR%\Arch-Assistant-App.zip'; " ^
  "$extract = '%TEMP_DIR%\app'; " ^
  "if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }; " ^
  "[System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $extract); " ^
  "if (-not (Test-Path '%TEMP_DIR%\app\Arch Assistant')) { " ^
  "  Write-Host '  ERROR: Archive missing folder'; exit 1; " ^
  "} " ^
  "Write-Host '  Extraction complete.'"

if errorlevel 1 (
    echo.
    echo  -----------------------------------------------
    echo   Archive is corrupted or incomplete.
    echo  -----------------------------------------------
    echo.
    pause
    goto :cleanup
)

echo.
echo [4/4] Installing to %INSTALL_DIR%...
echo.

if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%" 2>nul
mkdir "%INSTALL_DIR%" 2>nul

robocopy "%TEMP_DIR%\app\Arch Assistant" "%INSTALL_DIR%" /E /NFL /NDL /NJH /NJS /NC /NS >nul 2>&1
if errorlevel 8 (
    echo  -----------------------------------------------
    echo   Could not write to %INSTALL_DIR%
    echo   Close any open folders and try again.
    echo  -----------------------------------------------
    echo.
    pause
    goto :cleanup
)

echo  Creating shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$desktop = [Environment]::GetFolderPath('Desktop'); " ^
  "$sc = $ws.CreateShortcut($desktop + '\Arch Assistant.lnk'); " ^
  "$sc.TargetPath = '%INSTALL_DIR%\Arch.exe'; " ^
  "$sc.WorkingDirectory = '%INSTALL_DIR%'; " ^
  "$sc.Description = 'Arch AI Assistant'; " ^
  "$sc.Save(); " ^
  "Write-Host '  Desktop shortcut created.'"

echo.
echo  ============================================================
echo            INSTALLATION COMPLETE
echo  ============================================================
echo.
echo   Installed to: %INSTALL_DIR%
echo   Desktop shortcut created.
echo.
echo   First launch uses AI models included in the download (~2 GB).
echo   Models are bundled — no separate download needed after install.
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
