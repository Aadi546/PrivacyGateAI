# Verification record

## Windows execution

- Python 3.13.4, Windows 11 AMD64, Tesseract 5.4.0 with English data; CPU-only processing.
- Day 1 backend checkpoint: 27 tests passed before two additional security/gating tests were added.
- Day 2 backend checkpoint: **30 tests passed**, including real OCR, pixel masking, rebuilt scanned PDFs, native PDF redaction, three signature-indicator forms, QR detection, low-confidence rejection, failed/incomplete verification, original-byte integrity, technical compatibility gating, expiry, API authorization, and disabling inherited cloud tracing.
- Readable-mask revision: **37 tests passed** in 24.74 seconds, including all prior regressions plus mask formats, readable PDF content, unchanged pixels outside approved areas, JPEG input, textured-background rejection, tampered/missing replacements, and server-side replacement-rendering download gates. All three regenerated synthetic outputs (scanned Aadhaar, native PDF, PAN image) passed supported checks and were visually inspected.
- Built service-worker checks: **3 tests passed** for trusted-context pairing, token-bearing health requests, operation allowlisting, and controlled-portal access. These use a browser-API harness, not a live installed extension.
- WXT production build and TypeScript checks passed. The manifest includes the genuine side-panel entrypoint and restricted local permissions.
- The built React interface was exercised twice in the local Windows browser preview: pairing, scanned fixture analysis, initially unchecked findings, explicit approval, successful output verification, protected preview, and enabled download.
- The download action was invoked in the preview; the local API's exported binary and MIME/filename were independently verified by automated tests. A saved download in the in-app browser was not confirmed.
- A generated, verified synthetic protected PNG was manually selected through the mock portal's file chooser, then the consent and simulated submission controls produced **Demo submission complete**. No portal network upload occurs.
- Responsive layout checked at a 380-pixel viewport override: no horizontal document overflow. No browser console errors were captured in the checked preview flow.
- Three actual CPU runs are recorded in `benchmarks.md`; the readable-mask revision's observed totals were approximately 1.50–2.01 seconds for the synthetic scanned fixture.

## Remaining actual-device checks

Border-background correction: **42 tests passed** in 22.21 seconds. Synthetic regressions cover a red rule immediately below the number, exact preservation outside the masking rectangles, retained last-four pixels, bold/grayscale strokes, and rejection of lines/patterns crossing the replacement area. The originally reported image also passed an in-memory local check; no personal image or processed copy was saved in the repository. The running app was restarted and paired with the updated backend.

- Load the unpacked extension in desktop Chrome and run the real side-panel/content-script/service-worker flow using the platform checklist. The preview tests do not substitute for this installation check.
- The owner's friend runs the macOS setup and Day 1/Day 2 checkpoints directly on his Mac afterward. No Mac result is marked passed yet.

The supplied checkpoint scripts and browser checklist make those remaining checks repeatable without changing the approved architecture or scope.
