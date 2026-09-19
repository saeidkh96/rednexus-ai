param([Parameter(Mandatory=$true)][string]$Target)
$ErrorActionPreference = 'Stop'
$SourceRoot = Split-Path $PSScriptRoot -Parent
$TargetRoot = (Resolve-Path $Target).Path
if ($SourceRoot -eq $TargetRoot) { throw 'Extract the update into a separate folder before using this script.' }
if (!(Test-Path (Join-Path $TargetRoot 'rednexus\core.py'))) { throw 'Target is not the expected RedNexus v0 project.' }
$Running = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and
    $_.CommandLine.Contains($TargetRoot) -and $_.CommandLine -match 'rednexus'
}
if ($Running) { throw 'Stop the existing Nexus server and workers before upgrading.' }
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$BackupRoot = Join-Path (Split-Path $TargetRoot -Parent) ('rednexus-code-backup-' + $Stamp)
New-Item -ItemType Directory -Path $BackupRoot | Out-Null
$Database = Join-Path $TargetRoot 'data\nexus-v1.db'
if (Test-Path $Database) {
    $Python = Join-Path $TargetRoot '.venv\Scripts\python.exe'
    if (!(Test-Path $Python)) { throw 'Existing Python environment required to back up the database.' }
    $BackupDatabase = Join-Path $BackupRoot 'nexus-before-v2.db'
    & $Python -c 'import sqlite3,sys; a=sqlite3.connect(sys.argv[1]); b=sqlite3.connect(sys.argv[2]); a.backup(b); b.close(); a.close()' $Database $BackupDatabase
    if ($LASTEXITCODE -ne 0) { throw 'Database backup failed; source was not changed.' }
}
$Protected = @('.git','.venv','.env','config','data','backups','secrets','__pycache__','.pytest_cache','.ruff_cache')
# Back up and copy source only; never replace databases, local secrets or environments.
Get-ChildItem -LiteralPath $TargetRoot -Force | Where-Object {
    $_.Name -notin $Protected -and $_.Name -notlike '*.db*' -and $_.Name -notlike '.env.*' -and $_.Name -notlike 'credentials*.json'
} | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $BackupRoot -Recurse -Force }
Get-ChildItem -LiteralPath $SourceRoot -Force | Where-Object {
    $_.Name -notin $Protected -and $_.Name -notlike '*.db*' -and $_.Name -notlike '.env.*' -and $_.Name -notlike 'credentials*.json'
} | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $TargetRoot -Recurse -Force }
Write-Host "Source updated. Previous source: $BackupRoot"
Write-Host 'Existing databases, config, .env, .venv and .git were preserved. Run SETUP.ps1 from the target.'
Write-Host 'New config examples remain in this extracted release. Merge them manually if needed.'
