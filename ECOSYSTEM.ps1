param(
    [ValidateSet('serve','worker','bootstrap','migrate','sync-admin-grants')]
    [string]$Action = 'serve'
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $env:NEXUS_MANIFEST = Join-Path $PSScriptRoot 'config/projects-ecosystem.json'
    $env:NEXUS_ALLOW_HTTP = 'true'
    $env:NEXUS_ALLOWED_ORIGINS = 'http://127.0.0.1:8100,http://127.0.0.1:8111,http://127.0.0.1:8112,http://127.0.0.1:8113,http://127.0.0.1:8114'
    $python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path $python)) { throw 'Run SETUP.ps1 first.' }
    if ($Action -in @('bootstrap','sync-admin-grants')) {
        & $python -m rednexus.platform.cli $Action --workspace red --username saeid
    } else {
        & $python -m rednexus.platform.cli $Action
    }
    if ($LASTEXITCODE -ne 0) { throw "Nexus $Action failed. Read the error above." }
} finally { Pop-Location }
