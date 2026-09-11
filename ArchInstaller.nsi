; Arch Assistant Installer - NSIS Script
; TOR Browser-style with language selection
; Under 60MB - downloads 5GB model bundle post-install
;
; Build with:
;   "C:\Program Files (x86)\NSIS\makensis.exe" /V2 "C:\Users/trevo/Downloads/Arch-Repo\ArchInstaller.nsi"

!define APP_NAME "Arch Assistant"
!define APP_VERSION "1.0.0"
!define APP_WEBSITE "https://github.com/Wizzit-254/Arch-Assistant-Repo"

!include "LogicLib.nsh"
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

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "C:\Users/trevo/Downloads/Arch-Repo\LICENSE.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_PAGE_FINISH
!define MUI_FINISHPAGE_RUN "$INSTDIR\download.bat"
!define MUI_FINISHPAGE_RUN_NOTFOUND_MSG "Download script not found - please run from Start Menu"
!define MUI_FINISHPAGE_RUN_TEXT "Click Finish to run the download script"
!define MUI_FINISHPAGE_LINK "https://github.com/Wizzit-254/Arch-Assistant-Repo"
!define MUI_FINISHPAGE_LINK_TEXT "View repository source"

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Languages
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

; Launch download function
Function LaunchDownload
    Exec '"$INSTDIR\download.bat"'
FunctionEnd

; Descriptions
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "!Arch Assistant (required)" SecMain
    SectionIn RO
    
    SetOutPath "$INSTDIR"
    CreateDirectory "$INSTDIR"
    
    WriteRegStr HKLM "SOFTWARE\ArchAssistant" "Install_Dir" "$INSTDIR"
    WriteRegStr HKLM "SOFTWARE\ArchAssistant" "Version" "${APP_VERSION}"
    
    ; Include the download script
    File "C:\Users/trevo/Downloads\Arch-Repo\download.bat"
    
    ; Copy download script to install dir
    CopyFiles /FILESONLY "C:\Users/trevo/Downloads\Arch-Repo\download.bat" "$INSTDIR\download.bat"
    
    DetailPrint "Installer ready. Download script will run after installation."
SectionEnd

Section "Create Desktop Shortcut" SecDesktop
    CreateShortCut "$DESKTOP\Arch Assistant.lnk" "$INSTDIR\Arch.exe" "" "$INSTDIR\Arch.exe" 0
SectionEnd

Section "Create Start Menu Entry" SecStartMenu
    CreateDirectory "$SMPROGRAMS\Arch Assistant"
    CreateShortCut "$SMPROGRAMS\Arch Assistant\Arch Assistant.lnk" "$INSTDIR\Arch.exe" "" "$INSTDIR\Arch.exe" 0
    CreateShortCut "$SMPROGRAMS\Arch Assistant\Download.lnk" "$INSTDIR\download.bat" "" 
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
    
    Delete "$INSTDIR\download.bat"
    Delete "$INSTDIR\Arch.exe"
    Delete "$INSTDIR\Arch.ico"
    Delete "$INSTDIR\main.js"
    Delete "$INSTDIR\index.html"
    Delete "$INSTDIR\package.json"
    
    DeleteRegKey HKLM "SOFTWARE\ArchAssistant"
    DeleteRegValue HKCU "SOFTWARE\Microsoft\Windows\CurrentVersion\Run" "ArchAssistant"
    
    RMDir "$INSTDIR"
    RMDir "$LOCALAPPDATA\ArchAssistant"
SectionEnd
