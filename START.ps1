$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & .\.venv\Scripts\python.exe -m rednexus.platform.cli serve
    if ($LASTEXITCODE -ne 0) { throw 'API failed' }
} finally { Pop-Location }
