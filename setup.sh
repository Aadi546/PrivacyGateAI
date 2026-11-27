#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m backend.fixtures
(cd chrome-extension && npm ci && npm run build && npm run compile)
.venv/bin/python -c 'from backend.ocr import health; import json,sys; status=health(); print(json.dumps(status, indent=2)); sys.exit(0 if status.get("available") else 1)'
printf '%s\n' 'Setup complete. Confirm OCR is available, then run sh start.sh.'
