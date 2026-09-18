$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & .\.venv\Scripts\python.exe -m rednexus.platform.cli bootstrap --workspace red --username saeid
    if ($LASTEXITCODE -ne 0) { throw 'Bootstrap failed' }
} finally { Pop-Location }
