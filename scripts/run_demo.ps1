<#
.SYNOPSIS
  Starts the SpecGuard demo: the mock Time-to-Pay API and the backend, with a TEMPORARY database.

.DESCRIPTION
  - Uses (or creates) a project-local virtual environment; installs the backend requirements only if missing.
  - Starts the mock API (default port 9000, version 1.3.0 = the seeded overnight defect) and the backend
    (default port 8000). AI_PROVIDER comes from your environment or backend\.env and defaults to 'fake'.
  - The database is ALWAYS a temporary file under <repo>\.tmp\demo. It never uses backend\specguard.db or any other
    path; a -DatabasePath outside .tmp is refused before anything starts.
  - Reference data (policies, mock SUT versions) is seeded by the backend at startup; scripts\seed_demo.py then
    creates requirement RQ-014 (nothing is analysed or approved).
  - Stop everything with scripts\reset_demo.ps1.

.PARAMETER Python       Python to use. Default: <repo>\.venv\Scripts\python.exe (created if missing).
.PARAMETER SkipInstall  Never run pip; fail with instructions if packages are missing.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1
#>
[CmdletBinding()]
param(
  [int]$BackendPort = 8000,
  [int]$MockPort = 9000,
  [string]$MockVersion = '1.3.0',
  [string]$Python,
  [string]$DatabasePath,
  [switch]$SkipInstall,
  [switch]$NoSeed
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$TmpRoot = [System.IO.Path]::GetFullPath((Join-Path $Root '.tmp'))
$DemoDir = Join-Path $TmpRoot 'demo'
if (-not $DatabasePath) { $DatabasePath = Join-Path $DemoDir 'specguard-demo.db' }

function Assert-UnderTmp([string]$Path) {
  $full = [System.IO.Path]::GetFullPath($Path)
  $prefix = $TmpRoot.TrimEnd('\') + '\'
  if (-not $full.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use '$full': demo databases must live under '$TmpRoot'. Nothing was started."
  }
  return $full
}

$Db = Assert-UnderTmp $DatabasePath          # refuse BEFORE doing anything else
New-Item -ItemType Directory -Force -Path (Split-Path $Db) | Out-Null
$PidFile = Join-Path $DemoDir 'pids.json'

# --- Python and packages (project-local; nothing global) ---------------------------------------------------
if (-not $Python) {
  $Python = Join-Path $Root '.venv\Scripts\python.exe'
  if (-not (Test-Path $Python)) {
    $launcher = (Get-Command py -ErrorAction SilentlyContinue), (Get-Command python -ErrorAction SilentlyContinue) | Where-Object { $_ } | Select-Object -First 1
    if (-not $launcher) { throw 'Python 3.11+ was not found. Install it (user scope), then rerun.' }
    Write-Host "Creating virtual environment in $Root\.venv ..."
    if ($launcher.Name -like 'py*') { & $launcher.Source -3 -m venv (Join-Path $Root '.venv') } else { & $launcher.Source -m venv (Join-Path $Root '.venv') }
  }
}
if (-not (Test-Path $Python)) { throw "Python not found at $Python" }
& $Python -c "import fastapi, uvicorn, httpx, sqlalchemy, pydantic_settings" 2>$null
if ($LASTEXITCODE -ne 0) {
  if ($SkipInstall) { throw "Required packages are missing for $Python. Run: $Python -m pip install -r backend\requirements.txt" }
  Write-Host 'Installing backend requirements into the project-local environment ...'
  & $Python -m pip install -r (Join-Path $Root 'backend\requirements.txt')
  if ($LASTEXITCODE -ne 0) { throw 'pip install failed.' }
}

# --- Ports --------------------------------------------------------------------------------------------------
function Test-Listening([int]$Port) { [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) }
function Test-IsMock([int]$Port) {
  try { $v = Invoke-RestMethod "http://127.0.0.1:$Port/version" -TimeoutSec 2; return ($null -ne $v.meal_minimum) } catch { return $false }
}
if (Test-Listening $BackendPort) { throw "Port $BackendPort is in use. Run scripts\reset_demo.ps1 or pass -BackendPort." }
$mockRunning = Test-Listening $MockPort
if ($mockRunning -and -not (Test-IsMock $MockPort)) { throw "Port $MockPort is in use by something that is not the mock API. Pass -MockPort." }

$started = @()
function Start-Server([string]$Name, [string[]]$ServerArgs, [string]$WorkDir) {
  $log = Join-Path $DemoDir "$Name.log"
  $proc = Start-Process -FilePath $Python -ArgumentList $ServerArgs -WorkingDirectory $WorkDir -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $log -RedirectStandardError "$log.err"
  $script:started += $proc
  return $proc
}
function Stop-Started {
  foreach ($p in $script:started) {
    Get-CimInstance Win32_Process -Filter "ParentProcessId = $($p.Id)" -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  }
}

try {
  # --- Mock API ---------------------------------------------------------------------------------------------
  $env:MOCK_VERSION = $MockVersion
  if ($mockRunning) {
    Write-Host "Reusing the mock API already running on port $MockPort."
    Invoke-RestMethod -Method Post "http://127.0.0.1:$MockPort/admin/version" -ContentType 'application/json' -Body (@{ version = $MockVersion } | ConvertTo-Json) | Out-Null
    $mockPid = $null
  } else {
    $mock = Start-Server 'mock' @('-m', 'uvicorn', 'mock_api.main:app', '--host', '127.0.0.1', '--port', "$MockPort", '--log-level', 'warning') $Root
    $mockPid = $mock.Id
  }

  # --- Backend (temporary database; environment variables override backend\.env) ------------------------------
  if (-not $env:AI_PROVIDER) {
    $envFile = Join-Path $Root 'backend\.env'
    $fromFile = if (Test-Path $envFile) { (Select-String -Path $envFile -Pattern '^\s*AI_PROVIDER\s*=\s*(\S+)' | Select-Object -First 1) } else { $null }
    if (-not $fromFile) { $env:AI_PROVIDER = 'fake' }
  }
  $env:DATABASE_URL = 'sqlite:///' + ($Db -replace '\\', '/')
  $env:MOCK_API_BASE_URL = "http://127.0.0.1:$MockPort"
  $env:CORS_ORIGINS = 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174'
  $backend = Start-Server 'backend' @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort") (Join-Path $Root 'backend')

  # --- Wait for readiness -------------------------------------------------------------------------------------
  $deadline = (Get-Date).AddSeconds(40)
  $ready = $false
  while ((Get-Date) -lt $deadline -and -not $ready) {
    Start-Sleep -Milliseconds 500
    try { $ready = (Invoke-RestMethod "http://127.0.0.1:$BackendPort/health" -TimeoutSec 2).database -eq 'ok' } catch { $ready = $false }
  }
  if (-not $ready) { throw "The backend did not become healthy. See $DemoDir\backend.log and backend.log.err" }
  if (-not (Test-IsMock $MockPort)) { throw "The mock API did not become ready. See $DemoDir\mock.log.err" }

  @{ backend = $backend.Id; mock = $mockPid; backend_port = $BackendPort; mock_port = $MockPort; database = $Db } |
    ConvertTo-Json | Set-Content -Path $PidFile -Encoding UTF8
  if (-not $NoSeed) { & $Python (Join-Path $Root 'scripts\seed_demo.py') --backend "http://127.0.0.1:$BackendPort"; if ($LASTEXITCODE -ne 0) { throw 'Seeding failed.' } }
} catch {
  Stop-Started
  throw
}

$health = Invoke-RestMethod "http://127.0.0.1:$BackendPort/health"
Write-Host ''
Write-Host "SpecGuard demo is running (temporary database: $Db)"
Write-Host "  Backend API : http://127.0.0.1:$BackendPort   (docs: /docs)   AI provider: $($health.ai.provider), configured: $($health.ai.configured)"
Write-Host "  Mock API    : http://127.0.0.1:$MockPort   serving version $MockVersion"
Write-Host '  Frontend    : cd frontend; npm run dev   ->  http://127.0.0.1:5173'
if ($BackendPort -ne 8000) { Write-Host "                (backend is not on 8000: set `$env:VITE_API_BASE_URL='http://127.0.0.1:$BackendPort' first)" }
Write-Host '  Reset       : powershell -File scripts\reset_demo.ps1'
