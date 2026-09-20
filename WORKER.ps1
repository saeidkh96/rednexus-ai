$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & .\ECOSYSTEM.ps1 -Action worker
    if ($LASTEXITCODE -ne 0) { throw 'Worker failed' }
} finally { Pop-Location }
