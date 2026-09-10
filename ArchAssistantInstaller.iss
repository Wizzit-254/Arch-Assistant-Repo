; -- ArchAssistantInstaller.iss --
; Inno Setup script for Arch Assistant
; Usage: iscc ArchAssistantInstaller.iss /SIGNED_CERT_PATH="cert.pfx" /SIGNED_CERT_PASSWORD="pass"
;
; Prerequisites:
;   - Inno Setup (free from https://jrsoftware.org/isinfo.php)
;   - A code-signing certificate (from DigiCert, Sectigo, etc.)
;   - The Arch-Assistant-App.zip and Arch-Assistant-Models.zip (5.27 GB) release assets on GitHub
;
; To sign the installer (bypasses SmartScreen "Unknown Publisher"):
;   1. Set SignToolPath in Inno Setup Preferences -> Compiler -> Tools
;   2. Set SignTool to: signtool sign /f "$pfxpath" /p "$pfxpassword" /tr http://timestamp.digicert.com /td sha256 /fd sha256 /v $f
;   3. Or use the /SIGNED_* params when building

[Setup]
AppName=Arch Assistant
AppVersion=1.0.0
DefaultDirName={pf}\Arch Assistant
DefaultGroupName=Arch Assistant
OutputBaseFilename=ArchAssistantInstaller
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableStartupPrompt=yes

[Files]
Source: "Arch-Assistant-App.zip"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Code]
function InitializeSetup(): Boolean;
var
  ZipPath, ExtractDir, AppDir: String;
begin
  ZipPath := ExpandConstant('{tmp}\Arch-Assistant-App.zip');
  ExtractDir := ExpandConstant('{tmp}\arch-extract');
  AppDir := ExpandConstant('{pf}\Arch Assistant');

  if FileExists(ZipPath) then begin
    if DirExists(ExtractDir) then
      RemoveDirectory(ExtractDir, True);
    { Extract zip using PowerShell }
    Exec('powershell', '-NoProfile -ExecutionPolicy Bypass -Command "Add-Type -Assembly System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::ExtractToDirectory(\'' + ZipPath + '\', \'' + ExtractDir + '\')"', '', False, 0, SW_HIDE, ResultCode);
    if DirExists(ExtractDir + '\Arch Assistant') then begin
      if DirExists(AppDir) then
        RemoveDirectory(AppDir, True);
      CreateDir(AppDir);
      { Copy contents using robocopy }
      Exec('cmd', '/c robocopy "' + ExtractDir + '\Arch Assistant" "' + AppDir + '" /E /NFL /NDL /NJH /NJS /NC /NS >nul 2>&1', '', False, 0, SW_HIDE, ResultCode);
    end else begin
      MsgBox('Extraction failed. Archive may be corrupted.', mbError, MB_OK);
      Result := False;
      exit;
    end;
  end else begin
    { Download from GitHub }
    if MsgBox('No local zip found. Download from GitHub releases?', mbConfirmation, MB_YESNO) = MB_YES then begin
      ShellExec('open', 'https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/Arch-Assistant-App.zip', '', '', SW_SHOWNORMAL, ewNoError, ResultCode);
    end;
    Result := False;
    exit;
  end;

  { Create shortcut }
  Exec('powershell', '-NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $d = [Environment]::GetFolderPath(''Desktop''); $s = $ws.CreateShortcut($d + ''\Arch Assistant.lnk''); $s.TargetPath = ''' + AppDir + '\Arch.exe''; $s.WorkingDirectory = ''' + AppDir + '''; $s.Save()"', '', False, 0, SW_HIDE, ResultCode);

  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
end;

[Code]
function NextOnClick(Page: TWizardPage; Button: Integer): Boolean;
begin
  Result := True;
end;

[Files]
Source: "Arch-Assistant-App.zip"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Run]
Filename: "{pf}\Arch Assistant\Arch.exe"; Description: "Launch Arch Assistant"; Flags: nowait postinstall skipifdoesntexist

[Icons]
Name: "{group}\Arch Assistant"; Filename: "{pf}\Arch Assistant\Arch.exe"
Name: "{commondesktop}\Arch Assistant"; Filename: "{pf}\Arch Assistant\Arch.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: ""; Flags: unchecked
