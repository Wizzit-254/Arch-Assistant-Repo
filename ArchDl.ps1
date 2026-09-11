# Arch Assistant resumable downloader (run by the NSIS installer, not by hand).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ArchDl.ps1 "<url>" "<destDir>"
# Exit codes: 0 = downloaded OK, 1 = failed, 2 = not enough disk space.
param(
  [Parameter(Mandatory = $true)][string]$Url,
  [Parameter(Mandatory = $true)][string]$DestDir
)

$ErrorActionPreference = 'Stop'
$NeedBytes = 7516192768  # ~7GB: 5GB app + zip side-by-side during setup
$OutFile = Join-Path $DestDir 'Arch-Assistant-App.zip'

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

# Remove any stale partial file so BITS starts clean (BITS itself resumes
# across network drops inside the job, which is what matters on bad wifi).
if (Test-Path $OutFile) { Remove-Item $OutFile -Force }

try {
  Import-Module BitsTransfer -ErrorAction Stop
} catch {
  Write-Output 'BITS unavailable, using direct download with retries.'
  $attempt = 0
  while ($attempt -lt 200) {
    $attempt++
    try {
      Write-Output ('Direct attempt {0}...' -f $attempt)
      (New-Object System.Net.WebClient).DownloadFile($Url, $OutFile)
      if ((Get-Item $OutFile).Length -gt 100MB) { Write-Output 'Download complete.'; exit 0 }
    } catch {
      Write-Output ('Failed, retrying in 10s ({0})' -f $_.Exception.Message)
      Start-Sleep -Seconds 10
    }
  }
  exit 1
}

try {
  $job = Start-BitsTransfer -Source $Url -Destination $OutFile `
    -Asynchronous -Priority Foreground `
    -RetryInterval 60 -RetryTimeout 14400 `
    -Description 'Arch Assistant app bundle' -ErrorAction Stop
} catch {
  Write-Output ('Could not start download: ' + $_.Exception.Message)
  exit 1
}

$deadline = (Get-Date).AddHours(6)
$lastPct = -1
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 5
  try { $job = Get-BitsTransfer -JobId $job.JobId -ErrorAction Stop } catch { break }
  $state = $job.JobState.ToString()
  if ($state -in @('Transferring', 'Connecting', 'Queued', 'TransientError')) {
    if ($job.BytesTotal -gt 0) {
      $pct = [math]::Round(($job.BytesTransferred / $job.BytesTotal) * 100, 1)
      if ($pct -ne $lastPct) {
        $lastPct = $pct
        Write-Output ('Downloaded {0:N1} MB / {1:N1} MB ({2}%)' -f ($job.BytesTransferred / 1MB), ($job.BytesTotal / 1MB), $pct)
      }
    } else {
      Write-Output ('Connecting... transferred {0:N1} MB so far' -f ($job.BytesTransferred / 1MB))
    }
    continue
  }
  break
}

try { $job = Get-BitsTransfer -JobId $job.JobId -ErrorAction Stop } catch { $job = $null }
if ($job -and $job.JobState.ToString() -eq 'Transferred') {
  Complete-BitsTransfer -BitsJob $job -ErrorAction Stop
  $size = (Get-Item $OutFile).Length
  Write-Output ('Download complete: {0:N1} MB' -f ($size / 1MB))
  if ($size -lt 100MB) { Write-Output 'File too small, treating as failure.'; exit 1 }
  exit 0
}

if ($job) {
  Write-Output ('Download ended in state: ' + $job.JobState.ToString())
  try { Remove-BitsTransfer -BitsJob $job -ErrorAction SilentlyContinue } catch {}
}
exit 1
