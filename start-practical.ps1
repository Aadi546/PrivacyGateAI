$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$practicalPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $practicalPython)) { throw 'Run setup.ps1 first.' }
& $practicalPython -u -m backend.practical_server
