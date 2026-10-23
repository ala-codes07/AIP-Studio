# AIP Studio local startup. Run from PowerShell, in the extracted project folder.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
  Write-Host 'Creating a Python environment...' -ForegroundColor Cyan
  $venvDir = Join-Path $PSScriptRoot 'backend\.venv'
  $created = $false
  if (Get-Command py -ErrorAction SilentlyContinue) {
    try {
      & py -3 -m venv $venvDir 2>$null
      if (Test-Path $pythonExe) { $created = $true }
    } catch { Write-Host 'Trying the default Python installation…' }
  }
  if (-not $created -and (Get-Command python -ErrorAction SilentlyContinue)) {
    & python -m venv $venvDir
  }
  if (-not (Test-Path $pythonExe)) { throw 'Python 3.12+ is required. Install Python, then run again.' }
  & $pythonExe -m pip install -r (Join-Path $PSScriptRoot 'backend\requirements-dev.txt')
  if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
$envFile = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path $envFile)) {
  $template = Get-Content (Join-Path $PSScriptRoot '.env.example') -Raw
  $secret = & $pythonExe -c 'import secrets; print(secrets.token_urlsafe(48))'
  $template = $template.Replace('REPLACE_THIS_WITH_A_RANDOM_SECRET_OF_AT_LEAST_32_CHARACTERS', $secret.Trim())
  [System.IO.File]::WriteAllText($envFile, $template, [System.Text.UTF8Encoding]::new($false))
  Write-Host 'Generated a local .env and a new secret key.' -ForegroundColor Green
}
Set-Location (Join-Path $PSScriptRoot 'backend')
Write-Host 'Preparing the database...' -ForegroundColor Cyan
& $pythonExe -m app.scripts.bootstrap
if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed. If upgrading old data, back up the DB and check README.' }
Write-Host 'AIP Studio: http://localhost:8000/' -ForegroundColor Green
Write-Host 'API Docs:   http://localhost:8000/docs'
Write-Host 'Launching background scan worker (no Redis required)...' -ForegroundColor Cyan
$workerOut = Join-Path $PSScriptRoot 'worker.stdout.log'
$workerErr = Join-Path $PSScriptRoot 'worker.stderr.log'
$worker = Start-Process -FilePath $pythonExe -ArgumentList @('-m', 'app.scripts.scan_worker') -WorkingDirectory (Get-Location).Path -PassThru -WindowStyle Hidden -RedirectStandardOutput $workerOut -RedirectStandardError $workerErr
try {
  & $pythonExe -m uvicorn app.main:app --port 8000 --reload
} finally {
  if ($worker -and -not $worker.HasExited) {
    Stop-Process -Id $worker.Id -ErrorAction SilentlyContinue
  }
  Write-Host 'Scan worker stopped.' -ForegroundColor Cyan
}
