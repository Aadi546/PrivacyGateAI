# PrivacyGate AI — Setup and Verification

## Requirements

- Python 3.11+ for the local backend.
- Node.js 22.12+ and npm for the WXT extension. The supplied setup scripts also build/type-check the extension.
- Tesseract executable with English (`eng`) language data for local OCR.
- Desktop Chrome to load the extension and use the browser interfaces.
- Homebrew for the macOS Tesseract installation below.

Run commands from the repository root unless specified otherwise. Setup requires Internet access to download dependencies; the installed core makes no cloud inference requests. Windows checks are recorded in [practical verification](practical-verification.md). macOS scripts exist, but actual macOS runtime/browser verification remains pending.

## 1. Install dependencies

### Windows

Ensure `python` selects Python 3.11+ and `node`/`npm` are available. Install Tesseract and English data, then run setup:

```powershell
winget install --id UB-Mannheim.TesseractOCR --exact
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Open a new terminal if installation changed PATH.

### macOS

With Python, Node.js and Homebrew installed:

```sh
brew install tesseract
sh setup.sh
```

Setup creates `.venv`, installs Python requirements, generates six base synthetic fixtures, runs `npm ci`, builds/type-checks the extension and checks OCR. It does not install Python or Node.js. No paid API key is required.

### Tesseract configuration

The backend checks `TESSERACT_CMD` first, then PATH, the Windows `%ProgramFiles%\Tesseract-OCR\tesseract.exe` location and Homebrew paths `/usr/local/bin/tesseract` and `/opt/homebrew/bin/tesseract`.

If needed, set the appropriate override before starting the backend:

```powershell
$env:TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

```sh
export TESSERACT_CMD=/opt/homebrew/bin/tesseract
```

An invalid override fails explicitly. The Python package `pytesseract` alone does not install the executable or English data.

## 2. Run the expanded practical workspace

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-practical.ps1
```

macOS:

```sh
sh start-practical.sh
```

This starts the application/API on `127.0.0.1:8765` and a separate local recipient on `127.0.0.1:8766`. Open **http://127.0.0.1:8765/practical** and pair with the current terminal token. Keep the token out of public screenshots and recordings.

Keep the terminal open. Do not run another launcher on port 8765 simultaneously. Setup’s completion message references `start.ps1`/`start.sh` for the earlier flow; use the **practical launcher** above for the expanded two-service demo.

### Practical demo

1. Pair the workspace and click **Inspect sample PDF**. Built-in samples contain actual synthetic file bytes.
2. Review identifier findings, supported metadata and the configured recipient. Recipient submission has not happened yet.
3. Select identifiers to mask. Read the recipient-requirements notice and approve protection, including supported metadata removal. A recipient may require the complete document, not just its main ID.
4. Compare original/protected previews and the verification result. Required checks gate protected download/submission.
5. Download if desired, or select the verified copy for the final test upload. Separately approve sending it to the displayed local recipient.
6. Review the observed destination and matching-file receipt. Repeat in the other recipient mode with a new review and approval.
7. Try the scanned sample for OCR, JPEG sample for metadata and signature-indicator sample for blocked modification.
8. Clear sessions when finished. Ctrl+C stops both services.

The page has a 2 MB portal limit. The engine's 10 MB maximum does not override it. Image outputs are PNGs; JPEG-only recipient requirements would need a separately supported conversion strategy. Manual synthetic PDF selection and invalid-candidate replacement were browser-checked during comparison development; other file-picker/platform combinations still require testing.

### Compare address-proof alternatives

1. Choose **Compare two address proofs**, then **Inspect bank statement + electricity bill**, or select two supported local files.
2. Inspect both previews and the detected disclosure categories. Samples use the same fictional name and address; neither is valid address proof.
3. For each candidate, declare recipient acceptance and confirm the required name/current address. These are user declarations, not independently verified eligibility.
4. Click **Compare documents again**. The rule-based address-proof policy compares category counts by priority and explains a conditional suggestion, tie or inconclusive result. Document names do not determine the winner.
5. Choose a document for review. Only that candidate enters the existing protection, verification and separate upload flow. Some comparison categories, including balances/transactions, do not yet support automatic masking.
6. Changing candidates or suitability declarations clears downstream approvals. Failed extraction or expired sessions require reinspection.

## 3. Load the existing basic extension

The extension exposes the earlier masking workflow. Expanded metadata/recipient reporting remains in `/practical` pending integration.

The practical launcher also exposes the earlier portal. Alternatively, start only the earlier single-service flow using the platform command below, without another launcher already running:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

```sh
sh start.sh
```

1. In Chrome, open `chrome://extensions`, enable **Developer mode** and choose **Load unpacked**.
2. Select `chrome-extension/.output/chrome-mv3`, not the source directory or old launcher.
3. Open **http://127.0.0.1:8765/portal** and click **Check with PrivacyGate**.
4. Pair the side panel with the current token and confirm OCR availability.
5. Use **Try sample** for the scanned Aadhaar-like fixture, or select `sample-documents/aadhaar-scan.png` through the extension’s own picker.
6. Review findings, select the desired change, approve protection and create a separate copy.
7. Review the preview and verification. The synthetic sample can display `xxxx xxxx 0124` after masking.
8. Download the verified copy, manually select it on the earlier portal and approve simulated submission.

The earlier `/portal` submission **does not transmit a file**. Actual local uploads and receipts belong to `/practical`. The extension does not populate the website’s file input or universally intercept uploads.

The configured public extension identity lets the backend recognise its origin; its manifest key is not a private credential. Host permissions/origin checks are restricted to the demo. Use `127.0.0.1` in the walkthrough rather than assuming every localhost alias is permitted.

After building, **http://127.0.0.1:8765/** previews the earlier React interface, calling the backend directly. The extension proxies operations through its worker. Both differ from `/practical`.

## 4. Verification commands

### Backend tests

Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

macOS:

```sh
.venv/bin/python -m pytest -q
```

The comparison implementation recorded 64 passing backend tests on Windows. Running tests produces a new result on the actual machine; backend success does not establish installed-extension or file-picker compatibility.

### Extension checks

From the repository root:

```sh
cd chrome-extension
npm run compile
npm run build
cd ..
node --test tests/extension.test.mjs tests/practical-flow.test.mjs
```

The Node harness checks worker message authorisation, token handling and operation/portal restrictions. Rehearsing the installed extension is a separate browser check.

### Platform checkpoints

Windows:

```powershell
.\.venv\Scripts\python.exe scripts/checkpoint.py --day 1
.\.venv\Scripts\python.exe scripts/checkpoint.py --day 2
```

macOS:

```sh
.venv/bin/python scripts/checkpoint.py --day 1
.venv/bin/python scripts/checkpoint.py --day 2
```

Complete the manual [platform checklist](platform-checkpoints.md) separately. Scripts record backend/environment evidence, not browser success.

### Timing and fixtures

Windows:

```powershell
.\.venv\Scripts\python.exe scripts/practical_benchmark.py
```

macOS:

```sh
.venv/bin/python scripts/practical_benchmark.py
```

This writes a new `docs/practical-benchmarks.json` from synthetic local API runs, excluding browser rendering, user decisions and upload time. The earlier `scripts/benchmark.py` measures a different, masking-only scope. Regenerate base fixtures with the virtual-environment Python using `-m backend.fixtures`; expanded samples are generated by backend routes.

## Troubleshooting and cleanup

| Symptom | Action |
|---|---|
| Missing environment or built extension | Complete the platform setup script first |
| OCR unavailable | Check executable, English data and `TESSERACT_CMD`; restart after environment changes |
| Pairing rejected | Use the current process’s token; restarting invalidates the previous token |
| Port already in use | Stop the earlier launcher; the practical demo needs 8765 and 8766 |
| Different-origin upload fails | Keep the practical recipient on 8766 running |
| Expired session or four sessions open | Clear an inspection or reinspect; inactivity expiry is 15 minutes |
| Another document is processing | Wait; the prototype serialises processing |
| Protected output blocked | Read the limitation and use a supported clear fixture; do not bypass required checks |
| Signature indicator detected | Preserve the original; the prototype does not validate or repair signatures |

Sessions hold document bytes in process memory. Stopping the process clears that state; wrappers clean up library-managed temporary files. Downloads remain where the user saved them. These behaviours do not establish forensic erasure or protection against a compromised computer.

See the [project README](../README.md), [practical verification](practical-verification.md) and [known limitations](known-limitations.md) for functionality and evidence boundaries.
