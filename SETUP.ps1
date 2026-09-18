$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (!(Test-Path '.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create virtual environment' }
    }
    & .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    & .\.venv\Scripts\python.exe -m rednexus.platform.cli migrate
    if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
    Write-Host 'Setup complete. Run BOOTSTRAP.ps1 once, then START.ps1 and WORKER.ps1 in separate terminals.'
} finally { Pop-Location }
