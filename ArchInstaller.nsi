; Arch Assistant Installer v5 - NSIS Script
; TOR Browser-style wizard with language selection.
; Resilient on bad wifi: BITS download with resume + retries and live
; progress in the details pane. The small EXE downloads the ~1.85GB app
; bundle and extracts it as soon as the install location is confirmed
; (InstFiles stage, right after the Directory page).
; Requires ~7GB free during setup (5GB app + zip side-by-side).
;
; Build: "C:\Program Files (x86)\NSIS\makensis.exe" /V2 ArchInstaller.nsi

!define APP_NAME "Arch Assistant"
!define APP_VERSION "1.0.0"
!define APP_WEBSITE "https://github.com/Wizzit-254/Arch-Assistant-Repo"
!define APP_DOWNLOAD "https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/download/v1.0.0/Arch-Assistant-App.zip"

!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "Sections.nsh"
!include "MUI2.nsh"

!define MUI_ICON "C:\Users/trevo/Downloads/Arch-Assistant-App\Arch.ico"
!define MUI_UNICON "C:\Users/trevo/Downloads/Arch-Assistant-App\Arch.ico"
!define MUI_ABORTWARNING

; --- Page copy: set expectations up front ---
!define MUI_WELCOMEPAGE_TITLE "Arch Assistant ${APP_VERSION} Setup"
!define MUI_WELCOMEPAGE_TEXT "This wizard installs Arch Assistant.$\n$\nThe installer is small, but it downloads the ~1.85GB app bundle (AI models included) as soon as you confirm the install location. You need about 7GB of free disk space during setup (5GB for the app plus the download while it extracts).$\n$\nThe download resumes automatically if your connection drops, so it works even on unreliable wifi — just leave the installer running.$\n$\nClick Next to continue."

!define MUI_DIRECTORYPAGE_TEXT_TOP "Choose where to install Arch Assistant. Downloading and extraction begin immediately after you click Install on the next page. Make sure the drive has ~7GB free."
!define MUI_DIRECTORYPAGE_TEXT_DESTINATION "Install location"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "ArchAssistantSetup-x64.exe"
InstallDir "$LOCALAPPDATA\ArchAssistant"
InstallDirRegKey HKLM "SOFTWARE\ArchAssistant" "Install_Dir"
ShowInstDetails show
RequestExecutionLevel user

; --- Pages ---
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "C:\Users/trevo/Downloads/Arch-Repo\LICENSE.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; --- Languages ---
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "German"
!insertmacro MUI_LANGUAGE "French"
!insertmacro MUI_LANGUAGE "Spanish"
!insertmacro MUI_LANGUAGE "Russian"
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "Japanese"
!insertmacro MUI_LANGUAGE "Arabic"
!insertmacro MUI_LANGUAGE "Portuguese"
!insertmacro MUI_LANGUAGE "Italian"
!insertmacro MUI_LANGUAGE "Korean"
!insertmacro MUI_LANGUAGE "Turkish"
!insertmacro MUI_LANGUAGE "Dutch"
!insertmacro MUI_LANGUAGE "Polish"

; --- Descriptions ---
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "!Arch Assistant (required)" SecMain
    SectionIn RO

    SetOutPath "$INSTDIR"
    CreateDirectory "$INSTDIR"

    WriteRegStr HKLM "SOFTWARE\ArchAssistant" "Install_Dir" "$INSTDIR"
    WriteRegStr HKLM "SOFTWARE\ArchAssistant" "Version" "${APP_VERSION}"

    ; The downloader script ships INSIDE this EXE (no separate batch files).
    ; It runs here in the InstFiles stage, i.e. immediately after the user
    ; confirms the install location.
    DetailPrint "Preparing download (needs ~7GB free: 5GB app + download)..."
    InitPluginsDir
    SetOutPath $PLUGINSDIR
    File "ArchDl.ps1"
    SetOutPath "$INSTDIR"

    DetailPrint "Downloading app bundle (~1.85GB). Resumes on disconnects — leave this running."
    nsExec::ExecToLog 'powershell -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\ArchDl.ps1" "${APP_DOWNLOAD}" "$INSTDIR"'
    Pop $9

    ${If} $9 == 2
        MessageBox MB_ICONSTOP|MB_OK "Not enough free disk space.$\n$\nArch Assistant needs about 7GB free during setup (5GB for the app plus the installer download while it extracts).$\n$\nFree up space and run the installer again."
        Abort
    ${ElseIf} $9 != 0
        MessageBox MB_ICONSTOP|MB_OK "The download could not finish.$\n$\nYour connection may have dropped for a long time. Run the installer again later — it will retry automatically.$\n$\nManual download:$\n${APP_DOWNLOAD}"
        Abort
    ${EndIf}

    DetailPrint "Extracting app files (this takes a few minutes)..."
    nsExec::ExecToLog 'powershell -NoProfile -Command "Expand-Archive -Path ''$INSTDIR\Arch-Assistant-App.zip'' -DestinationPath ''$INSTDIR'' -Force"'
    Pop $9
    ${If} $9 != 0
        MessageBox MB_ICONSTOP|MB_OK "Extraction failed.$\n$\nTry running the installer again, or extract Arch-Assistant-App.zip with 7-Zip manually into:$\n$INSTDIR"
        Abort
    ${EndIf}

    Delete "$INSTDIR\Arch-Assistant-App.zip"
    DetailPrint "Installation complete!"
SectionEnd

Section "Create Desktop Shortcut" SecDesktop
    CreateShortCut "$DESKTOP\Arch Assistant.lnk" "$INSTDIR\Arch.exe" "" "$INSTDIR\Arch.exe" 0
SectionEnd

Section "Create Start Menu Entry" SecStartMenu
    CreateDirectory "$SMPROGRAMS\Arch Assistant"
    CreateShortCut "$SMPROGRAMS\Arch Assistant\Arch Assistant.lnk" "$INSTDIR\Arch.exe" "" "$INSTDIR\Arch.exe" 0
    CreateShortCut "$SMPROGRAMS\Arch Assistant\Uninstall.lnk" "$INSTDIR\uninstall.exe"
    WriteRegStr HKLM "SOFTWARE\ArchAssistant" "StartMenu" "1"
SectionEnd

Section "Pin to Taskbar" SecTaskbar
    WriteRegStr HKLM "SOFTWARE\ArchAssistant" "PinToTaskbar" "1"
SectionEnd

Section "Run at Windows Startup" SecStartup
    WriteRegStr HKCU "SOFTWARE\Microsoft\Windows\CurrentVersion\Run" "ArchAssistant" "$INSTDIR\Arch.exe"
SectionEnd

Section "Uninstall"
    ReadRegStr $INSTDIR HKLM "SOFTWARE\ArchAssistant" "Install_Dir"

    Delete "$DESKTOP\Arch Assistant.lnk"
    Delete "$SMPROGRAMS\Arch Assistant\Arch Assistant.lnk"
    Delete "$SMPROGRAMS\Arch Assistant\Uninstall.lnk"
    RMDir "$SMPROGRAMS\Arch Assistant"

    RMDir /r "$INSTDIR"
    RMDir "$LOCALAPPDATA\ArchAssistant"

    DeleteRegKey HKLM "SOFTWARE\ArchAssistant"
    DeleteRegValue HKCU "SOFTWARE\Microsoft\Windows\CurrentVersion\Run" "ArchAssistant"
SectionEnd
