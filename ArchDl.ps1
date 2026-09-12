# Arch Assistant resumable downloader (run by the NSIS installer, not by hand).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ArchDl.ps1 "<url>" "<destDir>"
#
# Cancel-safe: progress lives in Arch-Assistant-App.zip.part inside the
# install dir. Closing the installer mid-download keeps the partial file;
# re-running the installer to the SAME location resumes where it stopped.
#
# Engine: curl.exe (ships with Windows 10+) with auto-resume, infinite
# retries and a 25s stall guard, so dead-slow wifi fails fast and resumes
# instead of hanging. Falls back to a built-in HttpWebRequest loop if curl
# is missing. Progress lines are printed for the installer details pane.
#
# Exit codes: 0 = downloaded OK, 1 = failed, 2 = not enough disk space.
param(
  [Parameter(Mandatory = $true)][string]$Url,
  [Parameter(Mandatory = $true)][string]$DestDir
)

$ErrorActionPreference = 'Stop'
$NeedBytes = 7516192768  # ~7GB: 5GB app + zip side-by-side during setup
$OutFile = Join-Path $DestDir 'Arch-Assistant-App.zip.part'
$FinalFile = Join-Path $DestDir 'Arch-Assistant-App.zip'

function FreeBytes([string]$dir) {
  $q = (Split-Path $dir -Qualifier).TrimEnd(':')
  return (Get-PSDrive $q).Free
}

try {
  if (-not (Test-Path $DestDir)) { New-Item -ItemType Directory -Path $DestDir -Force | Out-Null }
  $free = FreeBytes $DestDir
  Write-Output ('Free space: {0:N1} GB (need ~7 GB)' -f ($free / 1GB))
  if ($free -lt $NeedBytes) {
    Write-Output 'LOWDISK'
    exit 2
  }
} catch {
  Write-Output ('Disk check failed: ' + $_.Exception.Message)
  exit 2
}

if (Test-Path $FinalFile) {
  Write-Output 'Found a completed download from a previous run - skipping download.'
  exit 0
}

# A previous run may have been closed mid-download, leaving its curl worker
# orphaned and still appending to our partial file. Stop it so two writers
# can never corrupt the file (our own curl starts later, so this is safe).
try {
  Get-CimInstance Win32_Process -Filter "Name='curl.exe'" -ErrorAction Stop | Where-Object {
    $_.CommandLine -like ('*' + $OutFile + '*')
  } | ForEach-Object {
    Write-Output ('Stopping leftover downloader from a previous run (PID {0}).' -f $_.ProcessId)
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 1
} catch { }

function Get-RemoteLength([string]$u) {
  try {
    $req = [System.Net.HttpWebRequest]::Create($u)
    $req.Method = 'HEAD'
    $req.UserAgent = 'ArchAssistant-Installer/7.0'
    $req.AllowAutoRedirect = $true
    $req.Timeout = 30000
    $resp = $req.GetResponse()
    try {
      if ($resp.ContentLength -gt 0) { return [long]$resp.ContentLength }
    } finally { $resp.Close() }
  } catch { }
  return -1
}

$remoteLen = Get-RemoteLength $Url
if ($remoteLen -gt 0) {
  Write-Output ('Remote size: {0:N1} MB' -f ($remoteLen / 1MB))
  if ((Test-Path $OutFile) -and ((Get-Item $OutFile).Length -gt $remoteLen)) {
    Write-Output 'Partial file is newer than the release - discarding it.'
    Remove-Item $OutFile -Force
  }
  if ((Test-Path $OutFile) -and ((Get-Item $OutFile).Length -ge $remoteLen)) {
    Write-Output 'Partial file already complete - skipping download.'
    Move-Item $OutFile $FinalFile -Force
    exit 0
  }
} elseif (Test-Path $OutFile) {
  Write-Output ('Resuming previous partial file ({0:N1} MB, total unknown)' -f ((Get-Item $OutFile).Length / 1MB))
}

function Start-CurlDownload {
  # NOTE: the numeric result is stored in $script:dlExit (a bare
  # `return <int>` would be polluted by progress lines, since PowerShell
  # returns ALL uncaptured function output).
  # NOTE 2: curl runs DIRECTLY (&), not via Start-Process: the .NET
  # Process.ExitCode property comes back empty for curl on this box,
  # while $LASTEXITCODE from a direct call is always reliable.
  $script:dlExit = 1
  $curlArgs = @('-L', '--fail',
    '--retry', '999', '--retry-delay', '3',
    '--retry-all-errors', '--retry-connrefused',
    '-C', '-',
    '--speed-time', '25', '--speed-limit', '1024',
    '--max-time', '14400',
    '-o', $OutFile, $Url)
  Write-Output 'Starting download (live speed/ETA below; Cancel anytime, progress is saved)...'
  & curl.exe @curlArgs
  $code = $LASTEXITCODE
  if ($code -ne 0) {
    Write-Output ("Downloader exited with code {0} - progress saved, will resume on re-run." -f $code)
  }
  $script:dlExit = $code
}

function Start-LegacyDownload {
  # Fallback when curl.exe is missing: HttpWebRequest with Range resume.
  $attempt = 0
  $deadline = (Get-Date).AddHours(4)
  while ((Get-Date) -lt $deadline) {
    $attempt++
    try {
      $req = [System.Net.HttpWebRequest]::Create($Url)
      $req.Method = 'GET'
      $req.UserAgent = 'ArchAssistant-Installer/7.0'
      $req.AllowAutoRedirect = $true
      $req.Timeout = 20000
      $req.ReadWriteTimeout = 20000
      $cur = 0
      if (Test-Path $OutFile) { $cur = (Get-Item $OutFile).Length }
      if ($cur -gt 0) { $req.AddRange($cur) }
      $resp = $req.GetResponse()
      try {
        if ($cur -gt 0 -and ([int]$resp.StatusCode) -eq 200) {
          $cur = 0
          Remove-Item $OutFile -Force -ErrorAction SilentlyContinue
        }
        $mode = [System.IO.FileMode]::Create
        if ($cur -gt 0) { $mode = [System.IO.FileMode]::Append }
        $fs = New-Object System.IO.FileStream($OutFile, $mode, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        try {
          $stream = $resp.GetResponseStream()
          $buf = New-Object byte[] 262144
          while (($n = $stream.Read($buf, 0, $buf.Length)) -gt 0) {
            $fs.Write($buf, 0, $n)
            $cur += $n
          }
        } finally { $fs.Close() }
      } finally { $resp.Close() }
      $script:dlExit = 0
      return
    } catch {
      Write-Output ('Stalled, retrying ({0}) - progress saved' -f $_.Exception.Message)
      Start-Sleep -Seconds ([math]::Min(30, 3 * $attempt))
    }
  }
  $script:dlExit = 1
}

$script:dlExit = 1
if (Get-Command 'curl.exe' -ErrorAction SilentlyContinue) {
  Start-CurlDownload
} else {
  Write-Output 'curl.exe not found - using built-in downloader.'
  Start-LegacyDownload
}
$code = $script:dlExit

if ($code -ne 0) {
  Write-Output 'Download did not finish - re-run the installer to the SAME folder to continue.'
  exit 1
}
if (-not (Test-Path $OutFile)) {
  Write-Output 'Download produced no file - re-run to retry.'
  exit 1
}
$size = (Get-Item $OutFile).Length
if ($remoteLen -gt 0 -and $size -lt $remoteLen) {
  Write-Output ('Incomplete ({0:N1} of {1:N1} MB) - re-run to resume.' -f ($size / 1MB), ($remoteLen / 1MB))
  exit 1
}
if ($size -lt 100MB) {
  Write-Output 'File too small, treating as failure.'
  exit 1
}
Write-Output ('Download complete: {0:N1} MB' -f ($size / 1MB))
Move-Item $OutFile $FinalFile -Force
exit 0
