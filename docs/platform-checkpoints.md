# Target-machine checkpoints

Windows and macOS behavior are directly checked on the actual target machines. Windows checks run in this workspace; the project's Mac tester (the owner's friend) runs the macOS checkpoints afterward on his device. Never mark a platform passed based on another platform's results.

## Day 1 — processing

1. Run the appropriate setup script. Confirm OCR reports `available: true` and `eng` is installed.
2. Run `scripts/checkpoint.py --day 1` using that machine's virtual-environment Python.
3. Confirm the report in `docs/checkpoints/<system>-day-1.json` identifies the actual machine's OS and architecture and reports passing tests.
4. Verify Tesseract auto-discovery: PATH, Windows default install, Intel Homebrew `/usr/local/bin/tesseract`, Apple Silicon Homebrew `/opt/homebrew/bin/tesseract`, or explicit `TESSERACT_CMD`. An invalid override must fail clearly.

## Day 2 — integration

1. Build and type-check the extension on the same machine. Start the local backend.
2. Load `chrome-extension/.output/chrome-mv3` in desktop Chrome.
3. Open the portal, click **Check with PrivacyGate**, and pair the side panel with the current terminal token.
4. Verify selecting a document in the panel leaves the website input empty.
5. Complete the scanned Aadhaar-like flow: approve its finding, redact, inspect the preview, download, manually select the protected copy on the portal, and simulate submission.
6. Repeat the entire flow a second time. Compare original/protected previews and confirm last-four preservation.
7. Confirm the signature fixture blocks modification, QR fixture warns, and oversized fixture reports incompatibility.
8. Restart the backend: the previous token must fail, and re-pairing with the new token must work.
9. Confirm clearing the document invalidates its backend session. Stop the backend after testing.
10. Run `scripts/checkpoint.py --day 2`. Record browser results below separately; the script covers the backend checks only.

| Machine | Backend checkpoint | Side-panel rehearsals | Reviewer |
|---|---|---|---|
| Windows | See generated Windows JSON reports | Record actual browser results | Workspace tester |
| macOS | Pending friend's actual-machine run | Pending two rehearsals | Project Mac tester |

Run `scripts/benchmark.py` for three timed CPU runs on the machine used for the presentation. Keep the resulting hardware-specific table with the checkpoint results.
