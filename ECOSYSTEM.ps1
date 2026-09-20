param(
    [ValidateSet('serve','worker','bootstrap','migrate','sync-admin-grants','doctor','preflight','redpa-login','credential-set','purge-memory')]
    [string]$Action = 'serve',
    [string]$Username = 'saeid',
    [string]$Workspace = 'red',
    [ValidateRange(1,8)][int]$Concurrency = 1,
    [string]$CredentialName = 'NEXUS_REDPA_TOKEN'
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $env:NEXUS_MANIFEST = Join-Path $PSScriptRoot 'config/projects-ecosystem.json'
    if (-not $env:NEXUS_DATABASE_URL) {
        $env:NEXUS_DATABASE_URL = 'sqlite:///' + ((Join-Path $PSScriptRoot 'data/nexus-v1.db') -replace '\\', '/')
    }
    $env:NEXUS_ALLOW_HTTP = 'true'
    if (-not $env:NEXUS_ALLOWED_ORIGINS) {
        $env:NEXUS_ALLOWED_ORIGINS = 'http://127.0.0.1:8100,http://127.0.0.1:8111,http://127.0.0.1:8112,http://127.0.0.1:8002,http://127.0.0.1:8114'
    }
    $python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path $python)) { throw 'Run SETUP.ps1 first.' }
    if ($Action -eq 'preflight') {
        & $python -m rednexus.platform.preflight
    } elseif ($Action -in @('bootstrap','sync-admin-grants')) {
        & $python -m rednexus.platform.cli $Action --workspace $Workspace --username $Username
    } elseif ($Action -eq 'worker') {
        & $python -m rednexus.platform.cli worker --concurrency $Concurrency
    } elseif ($Action -eq 'redpa-login') {
        & $python -m rednexus.platform.cli redpa-login --username $Username
    } elseif ($Action -eq 'credential-set') {
        & $python -m rednexus.platform.cli credential-set $CredentialName
    } else {
        & $python -m rednexus.platform.cli $Action
    }
    if ($LASTEXITCODE -ne 0) { throw "Nexus $Action failed. Read the error above." }
} finally { Pop-Location }
