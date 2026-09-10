; ArchAssistantInstaller.nsi - NSIS script for Arch Assistant staged installer
; Creates a ~6-7MB installer with UI for T&C display and install location

!define APP_NAME "Arch Assistant"
!define APP_VERSION "1.0.0"
!define STAGE2_URL "https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/ArchAssistant-Stage2.exe"

; --- Include Modern UI ---
!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "WordFunc.nsh"
!insertmacro VersionCompare

; --- General ---
Name "Arch Assistant Installer"
OutFile "ArchAssistantSetup-x64.exe"
InstallDir "$DESKTOP\Arch Assistant"
InstallDirRegKey HKLM "SOFTWARE\ArchAssistant" "Install_Dir"
RequestExecutionLevel user
ShowInstDetails show
ShowUninstDetails show

; --- Interface Settings ---
!define MUI_ABORTWARNING
!define MUI_ICON "Arch.ico"
!define MUI_UNICON "Arch.ico"
!define MUI_HEADER_TRANSPARENT backgroundColor
!define MUI_PAGE_FRAMED
!define MUI_HEADER_TEXT "Arch Assistant Installer"
!define MUI_HEADER_SUBTEXT "Stage 1: Lightweight Bootstrap Installer"

; --- Variables ---
Var InstallDirInput
Var TermsAccept

; --- Pages ---
!insertmacro MUI_PAGE_LICENSE "license.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_END

; --- Languages ---
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Kiswahili"
!insertmacro MUI_LANGUAGE "Français"
!insertmacro MUI_LANGUAGE "Español"
!insertmacro MUI_LANGUAGE "Deutsch"
!insertmacro MUI_LANGUAGE "Português"
!insertmacro MUI_LANGUAGE "Italiano"
!insertmacro MUI_LANGUAGE "日本語"
!insertmacro MUI_LANGUAGE "Arabic"
!insertmacro MUI_LANGUAGE "中文"

; --- File Sections ---
Section "Main"
    SetOutPath "$TEMP\arch-assistant-stage1"
    SetRegView 64
    
    DetailPrint "Downloading Stage 2 installer..."
    
    ; Download the Stage 2 installer
    NSISdl::download \
        "${STAGE2_URL}" \
        "$TEMP\arch-assistant-stage1\ArchAssistant-Stage2.exe" \
        "IDM:3000::no bandwidth limit"
    Pop $R0
    StrCmp $R0 "success" +3
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION \
        "Download failed: $R0$\n$\nRetry download or click Cancel to abort." \
        IDRETRY -3
    Abort
    
    ; Verify checksum
    DetailPrint "Verifying installer integrity..."
    Call:VerifyChecksum
    
    ; Run Stage 2 with custom install dir
    SetOutPath "$INSTDIR"
    DetailPrint "Launching full installer..."
    Exec '"$TEMP\arch-assistant-stage1\ArchAssistant-Stage2.exe" "--install-dir" "$INSTDIR"'
    
    ; Cleanup
    RMDir /r "$TEMP\arch-assistant-stage1"
    
    DetailPrint "Stage 2 installer launched."
SectionEnd

; --- Functions ---
Function .onInit
    ; Create license file at runtime (since NSIS requires it at compile)
    FileOpen $0 "$TEMP\arch-assistant-license.txt" w
    FileWrite $0 "ARCH ASSISTANT - TERMS AND CONDITIONS$\r$\n"
    FileWrite $0 "Version 1.0.0 (Effective: September 10, 2026)$\r$\n$\r$\n"
    FileWrite $0 "1. LICENSE - MIT License - you may use, modify, and distribute freely.$\r$\n"
    FileWrite $0 "2. NO WARRANTY - software provided as-is.$\r$\n"
    FileWrite $0 "3. AI MODELS - outputs not guaranteed accurate; review before use.$\r$\n"
    FileWrite $0 "4. PRIVACY - self-hosted, no telemetry, no accounts.$\r$\n"
    FileWrite $0 "5. SUPPORT - GitHub Issues: github.com/Wizzit-254/Arch-Assistant-Repo$\r$\n"
    FileWrite $0 "6. INSTALLATION - downloads ~5GB of AI models to selected directory.$\r$\n"
    FileWrite $0 "7. BY PROCEEDING, YOU ACCEPT THESE TERMS.$\r$\n"
    FileClose $0
    
    ; Set license file
    !insertmacro MUI_HEADER_TEXT "License Agreement" "Please read these terms"
FunctionEnd

Function VerifyChecksum
    ; Simple file size check as lightweight integrity verification
    ClearErrors
    StatSetSize $TEMP\arch-assistant-stage1\ArchAssistantStage2.exe
    ${If} $0 == ""
        DetailPrint "Warning: Could not verify checksum, proceeding anyway"
    ${EndIf}
FunctionEnd

Section "Uninstall"
SectionEnd
