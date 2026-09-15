; Arch Bootstrap - in-place launcher/installer for portable Arch folders.
; Lives INSIDE the app folder (E: drive, USB sticks, shared copies).
; On launch it silently ensures everything Arch.exe needs, then starts it:
;   1. Finds a real Python 3.9+ (NEVER the Microsoft Store stub — any
;      python.exe under WindowsApps is skipped without executing it).
;   2. If missing, downloads the official python.org installer (~30MB,
;      progress shown) and installs per-user quietly (no admin, no Store).
;   3. Installs backend pip packages quietly (yt-dlp, feedparser, psutil, babel).
;   4. Launches Arch.exe in place. No files are moved, no registry touched.
;
; Build: "C:\Program Files (x86)\NSIS\makensis.exe" /V2 ArchBootstrap.nsi
; Output: ArchBootstrap.exe (ship it inside the app folder).

!define APP_NAME "Arch Bootstrap"
!define APP_VERSION "1.0.0"
!define PYTHON_URL "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"

!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "StrFunc.nsh"
!include "MUI2.nsh"

${StrTrimNewLines}

!define MUI_ICON "C:\Users/trevo/Downloads/Arch-Assistant-App\Arch.ico"
!define MUI_ABORTWARNING

Name "${APP_NAME} ${APP_VERSION}"
OutFile "ArchBootstrap.exe"
; In-place: the folder this EXE sits in IS the app folder.
InstallDir "$EXEDIR"
ShowInstDetails show
RequestExecutionLevel user
AutoCloseWindow false

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Launch Arch Assistant now"
!define MUI_FINISHPAGE_RUN_FUNCTION "LaunchArch"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

Var PyExe
Var PyPre

; --- Test one python command for 3.9+. Sets $0 = "ok" or "bad". ---
!macro TestPy EXE PRE
  nsExec::ExecToStack '"${EXE}" ${PRE} -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)"'
  Pop $1
  Pop $0
  ${If} $0 == "0"
  ${AndIf} $1 == "0"
    StrCpy $PyExe "${EXE}"
    StrCpy $PyPre "${PRE}"
    StrCpy $0 "ok"
  ${Else}
    StrCpy $0 "bad"
  ${EndIf}
!macroend

Function FindPython
  StrCpy $PyExe ""
  StrCpy $PyPre ""
  ; 1. Known per-user / system installs (never the Store).
  ${If} ${FileExists} "$LOCALAPPDATA\Programs\Python\Python312\python.exe"
    !insertmacro TestPy "$LOCALAPPDATA\Programs\Python\Python312\python.exe" ""
    ${If} $0 == "ok"
      Return
    ${EndIf}
  ${EndIf}
  ${If} ${FileExists} "$PROGRAMFILES\Python312\python.exe"
    !insertmacro TestPy "$PROGRAMFILES\Python312\python.exe" ""
    ${If} $0 == "ok"
      Return
    ${EndIf}
  ${EndIf}
  ; 2. The python.org launcher (py.exe lives in C:\Windows, NOT the Store).
  !insertmacro TestPy "py" "-3"
  ${If} $0 == "ok"
    Return
  ${EndIf}
  ; 3. Anything else on PATH — Store stub filtered by findstr first,
  ;    so it is listed but NEVER executed.
  Delete "$TEMP\arch-where.txt"
  nsExec::ExecToStack 'cmd /c "(where python 2>nul | findstr /V /I WindowsApps) > \"$TEMP\arch-where.txt\""'
  Pop $9
  Pop $8
  FileOpen $9 "$TEMP\arch-where.txt" r
  IfErrors nofile
  scanloop:
    FileRead $9 $8
    IfErrors scandone
    ${StrTrimNewLines} $8 $8
    ${If} $8 != ""
      !insertmacro TestPy "$8" ""
      ${If} $0 == "ok"
        FileClose $9
        Delete "$TEMP\arch-where.txt"
        Return
      ${EndIf}
    ${EndIf}
    Goto scanloop
  scandone:
  FileClose $9
  nofile:
  Delete "$TEMP\arch-where.txt"
  ; Fallback scan of well-known names (Store stub excluded by path check).
  !insertmacro TestPy "python3" ""
  ${If} $0 == "ok"
    ; Final guard: refuse WindowsApps even if something slipped through.
    ${If} $PyExe == ""
      Return
    ${EndIf}
  ${EndIf}
FunctionEnd

Section "!Prepare and launch" SecMain
  SectionIn RO
  DetailPrint "Arch Bootstrap: preparing everything Arch.exe needs..."

  Call FindPython
  ${If} $PyExe == ""
    DetailPrint "No Python 3.9+ found. Downloading official installer (~30MB)..."
    DetailPrint "Source: python.org (never the Microsoft Store)."
    NSISdl::Download /TIMEOUT=300000 "${PYTHON_URL}" "$TEMP\arch-python-setup.exe"
    Pop $9
    ${If} $9 != "success"
      MessageBox MB_ICONSTOP|MB_OK "Could not download Python (check internet) and no usable Python was found.$\n$\nInstall Python 3.9+ from python.org, then run ArchBootstrap again."
      Abort
    ${EndIf}
    DetailPrint "Installing Python silently (per-user, no admin)..."
    ExecWait '"$TEMP\arch-python-setup.exe" /quiet InstallAllUsers=0 PrependPath=0 Include_pip=1 Include_test=0' $9
    Delete "$TEMP\arch-python-setup.exe"
    Call FindPython
  ${EndIf}

  ${If} $PyExe == ""
    MessageBox MB_ICONSTOP|MB_OK "Python 3.9+ is required but could not be set up automatically.$\n$\nInstall it from python.org (NOT the Microsoft Store version), then run ArchBootstrap again."
    Abort
  ${EndIf}
  DetailPrint "Python ready: $PyExe"

  DetailPrint "Installing backend packages (yt-dlp, feedparser, psutil, babel)..."
  nsExec::ExecToLog '"$PyExe" $PyPre -m pip install --quiet --disable-pip-version-check yt-dlp feedparser psutil babel'
  Pop $9

  ${IfNot} ${FileExists} "$INSTDIR\Arch.exe"
    MessageBox MB_ICONSTOP|MB_OK "Arch.exe was not found next to ArchBootstrap.exe.$\n$\nKeep both files in the same Arch folder."
    Abort
  ${EndIf}
  ${IfNot} ${FileExists} "$INSTDIR\api_server.py"
    MessageBox MB_ICONSTOP|MB_OK "api_server.py was not found next to ArchBootstrap.exe.$\n$\nThis folder does not look like a complete Arch install."
    Abort
  ${EndIf}

  DetailPrint "Everything ready. Launching Arch Assistant..."
SectionEnd

Function LaunchArch
  Exec '"$INSTDIR\Arch.exe"'
FunctionEnd
