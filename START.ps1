$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & .\ECOSYSTEM.ps1 -Action serve
    if ($LASTEXITCODE -ne 0) { throw 'API failed' }
} finally { Pop-Location }
