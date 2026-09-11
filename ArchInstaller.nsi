; Arch Assistant Installer v3 - NSIS Script
; TOR Browser-style with language selection
; Downloads + extracts 5GB app bundle during install (no external scripts)
;
; Build with:
;   "C:\Program Files (x86)\NSIS\makensis.exe" /V2 "C:\Users/trevo/Downloads/Arch-Repo\ArchInstaller.nsi"

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
    
    ; Download the 5GB app bundle using NSISdl
    DetailPrint "Downloading Arch Assistant app bundle (~5GB) from GitHub..."
    DetailPrint "This may take 10-30 minutes depending on your connection."
    
    NSISDL::Download /TIMEOUT=300000 "${APP_DOWNLOAD}" "$INSTDIR\Arch-Assistant-App.zip"
    Pop $9
    ${If} $9 == "success"
        DetailPrint "Download complete. Extracting..."
        
        ; Extract using PowerShell Expand-Archive
        DetailPrint "Extracting archive..."
        nsExec::ExecToLog 'powershell.exe -NoProfile -Command "Expand-Archive -Path ''$INSTDIR\Arch-Assistant-App.zip'' -DestinationPath ''$INSTDIR'' -Force"'
        
        ; Delete the zip
        Delete "$INSTDIR\Arch-Assistant-App.zip"
        
        DetailPrint "Installation complete!"
    ${Else}
        DetailPrint "Download failed: $9"
        MessageBox MB_ICONSTOP|MB_OK "Download failed: $9$\n$\nPlease check your internet connection and try again.$\n$\nManual download:$\n${APP_DOWNLOAD}"
        Abort
    ${EndIf}
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
