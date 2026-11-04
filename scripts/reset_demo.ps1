<#
.SYNOPSIS
  Resets the SpecGuard demo: stops the demo servers, deletes ONLY the temporary demo database, and puts the
  mock API back on version 1.3.0.

.DESCRIPTION
  Safety: it only ever deletes 'specguard-demo.db' (plus its -wal/-shm) under <repo>\.tmp\demo. Any other
  -DatabasePath is refused before anything is touched; the development database is never involved.
  It stops only the process IDs recorded by run_demo.ps1, and only if they are still uvicorn processes.

.PARAMETER KeepMockRunning  Reset the mock to 1.3.0 but leave it running.
.PARAMETER WhatIf           Show what would happen without doing it.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\reset_demo.ps1
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$DatabasePath,
  [switch]$KeepMockRunning
)

$ErrorActionPreference = 'Stop'
$savedWhatIf = $WhatIfPreference; $WhatIfPreference = $false   # keep module auto-import quiet under -WhatIf
Import-Module CimCmdlets -ErrorAction SilentlyContinue
$WhatIfPreference = $savedWhatIf
$Root = Split-Path -Parent $PSScriptRoot
$TmpRoot = [System.IO.Path]::GetFullPath((Join-Path $Root '.tmp'))
$DemoDir = Join-Path $TmpRoot 'demo'
if (-not $DatabasePath) { $DatabasePath = Join-Path $DemoDir 'specguard-demo.db' }

function Assert-UnderTmp([string]$Path) {
  $full = [System.IO.Path]::GetFullPath($Path)
  $prefix = $TmpRoot.TrimEnd('\') + '\'
  if (-not $full.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to touch '$full': only databases under '$TmpRoot' may be reset. Nothing was changed."
  }
  return $full
}

$Db = Assert-UnderTmp $DatabasePath          # refuse BEFORE doing anything else
$PidFile = Join-Path $DemoDir 'pids.json'
$info = if (Test-Path $PidFile) { Get-Content $PidFile -Raw | ConvertFrom-Json } else { $null }

function Get-UvicornTree([int]$RootId) {
  # The venv python.exe is a launcher: the process that listens is its child, so stop the whole tree,
  # but only processes whose command line is a uvicorn server.
  $found = @()
  $queue = [System.Collections.Generic.Queue[int]]::new()
  $queue.Enqueue($RootId)
  while ($queue.Count -gt 0) {
    $current = $queue.Dequeue()
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $current" -ErrorAction SilentlyContinue
    if ($proc -and $proc.CommandLine -match 'uvicorn') { $found += $current }
    foreach ($child in (Get-CimInstance Win32_Process -Filter "ParentProcessId = $current" -ErrorAction SilentlyContinue)) { $queue.Enqueue([int]$child.ProcessId) }
  }
  return $found
}

function Stop-Uvicorn([object]$ProcessId, [string]$Label) {
  if (-not $ProcessId) { return }
  $ids = @(Get-UvicornTree ([int]$ProcessId))
  if ($ids.Count -eq 0) { Write-Host "Left PID $ProcessId alone: it is no longer a uvicorn process."; return }
  foreach ($id in $ids) {
    if ($PSCmdlet.ShouldProcess("$Label (PID $id)", 'Stop')) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue; Write-Host "Stopped $Label (PID $id)." }
  }
}

# 1. mock back to 1.3.0 (while it is still reachable)
if ($info) {
  try {
    if ($PSCmdlet.ShouldProcess("mock API on port $($info.mock_port)", 'Reset to version 1.3.0')) {
      Invoke-RestMethod -Method Post "http://127.0.0.1:$($info.mock_port)/admin/version" -ContentType 'application/json' -Body (@{ version = '1.3.0' } | ConvertTo-Json) -TimeoutSec 3 | Out-Null
      Write-Host 'Mock API reset to version 1.3.0.'
    }
  } catch { Write-Host 'Mock API is not reachable; the next run_demo starts it on 1.3.0.' }
  # 2. stop the servers this demo started
  Stop-Uvicorn $info.backend 'backend'
  if (-not $KeepMockRunning) { Stop-Uvicorn $info.mock 'mock API' }  # a reused mock has no recorded PID and keeps running
} else {
  Write-Host 'No recorded demo servers.'
}

# 3. delete ONLY the temporary demo database files
foreach ($suffix in '', '-wal', '-shm') {
  $file = Assert-UnderTmp ($Db + $suffix)
  if ((Split-Path $file -Leaf) -notlike 'specguard-demo.db*') { throw "Refusing to delete '$file': not a demo database file." }
  if (Test-Path $file) {
    if ($PSCmdlet.ShouldProcess($file, 'Delete temporary demo database file')) { Remove-Item -LiteralPath $file -Force; Write-Host "Deleted $file" }
  }
}
if ($info -and $PSCmdlet.ShouldProcess($PidFile, 'Remove')) { Remove-Item -LiteralPath $PidFile -Force }
Write-Host 'Demo reset. Start it again with: powershell -File scripts\run_demo.ps1'
