# Arch Assistant resumable downloader (run by the NSIS installer, not by hand).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ArchDl.ps1 "<url>" "<destDir>"
#
# Cancel-safe: progress lives in Arch-Assistant-App.zip.part inside the
# install dir. Closing the installer mid-download keeps the partial file;
# re-running the installer to the SAME location resumes where it stopped.
#
# Exit codes: 0 = downloaded OK, 1 = failed, 2 = not enough disk space,
#             3 = file complete but corrupt (delete + re-run downloads fresh).
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

function Get-RemoteInfo([string]$u) {
  # Resolve redirects first so Range requests hit the final host directly.
  $req = [System.Net.HttpWebRequest]::Create($u)
  $req.Method = 'HEAD'
  $req.UserAgent = 'ArchAssistant-Installer/6.0'
  $req.AllowAutoRedirect = $true
  $req.Timeout = 30000
  try {
    $resp = $req.GetResponse()
    try {
      return @{ Url = $resp.ResponseUri.ToString(); Length = $resp.ContentLength }
    } finally { $resp.Close() }
  } catch {
    return @{ Url = $u; Length = -1 }
  }
}

$info = Get-RemoteInfo $Url
$realUrl = $info.Url
$remoteLen = [long]$info.Length
if ($remoteLen -gt 0) {
  Write-Output ('Remote size: {0:N1} MB' -f ($remoteLen / 1MB))
} else {
  Write-Output 'Remote size unknown - downloading without resume validation.'
}

$existing = 0
if (Test-Path $OutFile) { $existing = (Get-Item $OutFile).Length }
if (Test-Path $FinalFile) {
  # Previous run finished the download but not extraction.
  Write-Output 'Found a completed download from a previous run - skipping download.'
  exit 0
}
if ($existing -gt 0) {
  if ($remoteLen -gt 0 -and $existing -ge $remoteLen) {
    Write-Output 'Partial file already complete - verifying by size, skipping download.'
    Move-Item $OutFile $FinalFile -Force
    exit 0
  }
  if ($remoteLen -gt 0) {
    Write-Output ('Resuming at {0:N1} MB of {1:N1} MB ({2}%)' -f ($existing / 1MB), ($remoteLen / 1MB), [math]::Round($existing / $remoteLen * 100, 1))
  } else {
    Write-Output ('Resuming at {0:N1} MB (total unknown)' -f ($existing / 1MB))
  }
}

$deadline = (Get-Date).AddHours(4)
$attempt = 0
$lastPct = -1
while ((Get-Date) -lt $deadline) {
  $attempt++
  try {
    $req = [System.Net.HttpWebRequest]::Create($realUrl)
    $req.Method = 'GET'
    $req.UserAgent = 'ArchAssistant-Installer/6.0'
    $req.AllowAutoRedirect = $true
    $req.Timeout = 30000
    $req.ReadWriteTimeout = 60000
    $cur = 0
    if (Test-Path $OutFile) { $cur = (Get-Item $OutFile).Length }
    if ($cur -gt 0) { $req.AddRange($cur) }
    $resp = $req.GetResponse()
    try {
      $status = [int]$resp.StatusCode
      if ($cur -gt 0 -and $status -eq 200) {
        # Server ignored Range - restart from scratch to avoid corruption.
        Write-Output 'Server refused resume - restarting download from 0.'
        $cur = 0
        Remove-Item $OutFile -Force -ErrorAction SilentlyContinue
      } elseif ($cur -gt 0 -and $status -ne 206) {
        throw "Unexpected status $status for resume"
      }
      if ($remoteLen -le 0 -and $resp.ContentLength -gt 0) {
        $remoteLen = $resp.ContentLength + $cur
        Write-Output ('Remote size: {0:N1} MB' -f ($remoteLen / 1MB))
      }
      $mode = [System.IO.FileMode]::Create
      if ($cur -gt 0) { $mode = [System.IO.FileMode]::Append }
      $fs = New-Object System.IO.FileStream($OutFile, $mode, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
      try {
        $stream = $resp.GetResponseStream()
        $buf = New-Object byte[] 1048576
        $lastBeat = Get-Date
        while ($true) {
          $n = $stream.Read($buf, 0, $buf.Length)
          if ($n -le 0) { break }
          $fs.Write($buf, 0, $n)
          $cur += $n
          $lastBeat = Get-Date
          if ($remoteLen -gt 0) {
            $pct = [math]::Round($cur / $remoteLen * 100, 1)
            if ($pct -ne $lastPct -and ([math]::Floor($pct) % 2 -eq 0 -or $pct -ge 99.9)) {
              $lastPct = $pct
              Write-Output ('Downloaded {0:N1} MB / {1:N1} MB ({2}%) - Cancel anytime, progress is saved' -f ($cur / 1MB), ($remoteLen / 1MB), $pct)
            }
          } elseif ($cur % (50 * 1MB) -lt 1048576) {
            Write-Output ('Downloaded {0:N1} MB (total unknown) - Cancel anytime, progress is saved' -f ($cur / 1MB))
          }
          if (((Get-Date) - $lastBeat).TotalSeconds -gt 90) { throw 'Stalled (no data for 90s)' }
        }
      } finally { $fs.Close() }
      $done = (Test-Path $OutFile) -and (($remoteLen -le 0) -or ((Get-Item $OutFile).Length -ge $remoteLen))
      if ($done) {
        $size = (Get-Item $OutFile).Length
        Write-Output ('Download complete: {0:N1} MB' -f ($size / 1MB))
        if ($size -lt 100MB) { Write-Output 'File too small, treating as failure.'; exit 1 }
        Move-Item $OutFile $FinalFile -Force
        exit 0
      }
      Write-Output 'Stream ended early - will resume.'
    } finally { $resp.Close() }
  } catch {
    Write-Output ('Interrupted ({0}) - progress saved, re-run to resume.' -f $_.Exception.Message)
  }
  $wait = [math]::Min(60, 5 * $attempt)
  Write-Output ("Retrying in {0}s... (close the installer any time; nothing is lost)" -f $wait)
  Start-Sleep -Seconds $wait
}

Write-Output 'Out of retries for this run - re-run the installer to the SAME folder to continue.'
exit 1
