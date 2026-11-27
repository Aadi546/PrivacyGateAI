$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$prototypePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $prototypePython)) { throw 'Run setup.ps1 first to create the project environment.' }
& $prototypePython -m backend
