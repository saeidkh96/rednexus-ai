param([Parameter(Mandatory=$true)][string]$Target)
$ErrorActionPreference = 'Stop'
$SourceRoot = Split-Path $PSScriptRoot -Parent
$TargetRoot = (Resolve-Path $Target).Path
if ($SourceRoot -eq $TargetRoot) { throw 'Extract the update into a separate folder before using this script.' }
if (!(Test-Path (Join-Path $TargetRoot 'rednexus\core.py'))) { throw 'Target is not the expected RedNexus v0 project.' }
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$BackupRoot = Join-Path (Split-Path $TargetRoot -Parent) ('rednexus-code-backup-' + $Stamp)
New-Item -ItemType Directory -Path $BackupRoot | Out-Null
$Protected = @('.git','.venv','.env','data','backups','__pycache__','.pytest_cache','.ruff_cache')
# Back up and copy source only; never replace databases, local secrets or environments.
Get-ChildItem -LiteralPath $TargetRoot -Force | Where-Object {
    $_.Name -notin $Protected -and $_.Name -notlike '*.db*'
} | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $BackupRoot -Recurse -Force }
Get-ChildItem -LiteralPath $SourceRoot -Force | Where-Object {
    $_.Name -notin $Protected -and $_.Name -notlike '*.db*'
} | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $TargetRoot -Recurse -Force }
Write-Host "Source updated. Previous source: $BackupRoot"
Write-Host 'Existing databases, .env, .venv and .git were preserved. Run SETUP.ps1 from the target.'
