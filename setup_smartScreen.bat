@echo off
setlocal EnableExtensions
title Arch Assistant - SmartScreen Certificate Setup
color 0A

echo.
echo  ============================================================
echo         ARCH ASSISTANT - SMARTSCREEN BYPASS SETUP
echo  ============================================================
echo.
echo  This script creates a self-signed code signing certificate
echo  and installs it in the Trusted Root Certification Authorities
echo  store, which bypasses the SmartScreen "Unknown Publisher"
echo  warning on this machine.
echo.
echo  NOTE: This certificate is for your machine only. Other users
echo  will still see the warning unless they install this cert too.
echo.

REM Check for admin privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] This script requires administrator privileges.
    echo  Please run as Administrator.
    echo.
    pause
    exit /b 1
)

echo [1/4] Creating self-signed code signing certificate...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject 'CN=Arch Assistant Publisher' -KeyUsage DigitalSignature -KeyLength 2048 -FriendlyName 'Arch Assistant Code Signing' -CertStoreLocation 'Cert:\CurrentUser\My'; " ^
  "$pwd = Read-Host -AsSecureString -Prompt 'Enter password for export (e.g., ArchPass123)'; " ^
  "$path = \"$env:USERPROFILE\Downloads\Arch Assistant\arch_signing_cert.pfx\"; " ^
  "Export-PfxCertificate -Cert $cert -FilePath $path -Password $pwd; " ^
  "Write-Host '  Certificate created: ' $path"

if errorlevel 1 (
    echo  [ERROR] Failed to create certificate.
    pause
    exit /b 1
)

echo.
echo [2/4] Installing certificate in Trusted Root...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject 'CN=Arch Assistant Publisher' -KeyUsage DigitalSignature -KeyLength 2048 -FriendlyName 'Arch Assistant' -CertStoreLocation 'Cert:\CurrentUser\My'; " ^
  "$thumb = $cert.Thumbprint; " ^
  "Copy-Item Cert:\CurrentUser\My\$thumb Cert:\LocalMachine\Root; " ^
  "Write-Host '  Certificate installed in Trusted Root CA store'"

if errorlevel 1 (
    echo  [WARNING] Could not install in Trusted Root. SmartScreen may still warn.
)

echo.
echo [3/4] Signing ArchAssistantInstaller.exe...
echo.

set "SIGN_PWD="
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$pwd = Read-Host -AsSecureString -Prompt 'Enter certificate password'; " ^
  "$b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($pwd); " ^
  "$str = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b); " ^
  "Set-Content -Path \"$env:TEMP\sign_pwd.txt\" -Value $str; " ^
  "[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)"

set /p SIGN_PWD=<"%TEMP%\sign_pwd.txt"
del "%TEMP%\sign_pwd.txt"

if exist "%USERPROFILE%\Downloads\Arch Assistant\arch_signing_cert.pfx" (
    signtool sign /f "%USERPROFILE%\Downloads\Arch Assistant\arch_signing_cert.pfx" /p "%SIGN_PWD%" /t http://timestamp.digicert.com /v "%~dp0ArchAssistantInstaller.exe" 2>&1
    if errorlevel 1 (
        echo  [WARNING] signtool not found. Install Windows SDK to sign executables.
        echo  You can still use install.bat as an alternative installer.
    )
)

echo.
echo [4/4] Done!
echo.
echo  SmartScreen bypass installed on this machine.
echo  On first run, you may still need to click "More info" then "Run anyway"
echo  for the first few launches until reputation builds.
echo.
echo  Alternative: Use install.bat which is a script-based installer
echo  and does not require code signing.
echo.
pause
exit /b 0
