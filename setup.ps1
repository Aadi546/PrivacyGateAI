$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
& .\.venv\Scripts\python.exe -m backend.fixtures
Push-Location -LiteralPath (Join-Path $PSScriptRoot 'chrome-extension')
try {
  npm ci
  if ($LASTEXITCODE -ne 0) { throw 'Node dependency installation failed.' }
  npm run build
  if ($LASTEXITCODE -ne 0) { throw 'Extension build failed.' }
  npm run compile
  if ($LASTEXITCODE -ne 0) { throw 'TypeScript check failed.' }
} finally { Pop-Location }
& .\.venv\Scripts\python.exe -c "from backend.ocr import health; import json,sys; status=health(); print(json.dumps(status, indent=2)); sys.exit(0 if status.get('available') else 1)"
if ($LASTEXITCODE -ne 0) { throw 'Tesseract OCR is not ready. Install the engine and English data or correct TESSERACT_CMD.' }
Write-Output 'Setup complete. Confirm OCR is available, then run .\start.ps1.'
