$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $NexusPython = '.\.venv\Scripts\python.exe'
    & $NexusPython -m ruff check rednexus tests
    if ($LASTEXITCODE -ne 0) { throw 'Lint failed' }
    & $NexusPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    & $NexusPython -m rednexus.platform.cli demo
    if ($LASTEXITCODE -ne 0) { throw 'Platform demo failed' }
    & $NexusPython -m rednexus.demo
    if ($LASTEXITCODE -ne 0) { throw 'Legacy demo failed' }
} finally { Pop-Location }
