$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & .\.venv\Scripts\python.exe -m rednexus.platform.cli worker
    if ($LASTEXITCODE -ne 0) { throw 'Worker failed' }
} finally { Pop-Location }
