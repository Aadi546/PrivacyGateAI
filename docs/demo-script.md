# Three-to-five-minute demonstration

## Preparation

Start the backend, load the built extension, open the controlled scholarship portal, and pair the side panel. Confirm OCR is ready. Use only the supplied synthetic documents. Keep the terminal's session token out of presentation screenshots.

## Main flow — about three minutes

1. **Problem (20 seconds):** “An upload often shares more than a website needs. PrivacyGate helps inspect a document before sharing it, locally.”
2. **Browser integration (20 seconds):** Click **Check with PrivacyGate** beside the upload input. Show the side panel and the still-empty website input. Explain that requirements came from this controlled portal's data attributes.
3. **Local analysis (30 seconds):** Choose the scanned Aadhaar-like sample. Point out the document classification, first-eight-digit masking recommendation, optional contact findings, rule-based label, and QR/authentication notes.
4. **User decision (20 seconds):** Select only the Aadhaar finding, approve the change, and create the protected copy. Nothing is masked automatically.
5. **Verification (40 seconds):** Compare original and output. The first eight digits are removed, last four preserved. Show the verification report and the now-enabled download button. Explain that these are supported checks, not a guarantee of authenticity or acceptance.
6. **Return to the web (30 seconds):** Download, manually choose the protected PNG on the portal, approve, and simulate submission. Explain that the mock does not transmit the file.

## Backup beats — up to two minutes

- Signature-indicator PDF: structural indicator warning; modification disabled.
- QR sample: warning that QR contents may still identify the person; recommend an official masked document.
- Oversized sample: mismatch with the 2 MB portal limit before any submission.
- Expand the tool trace: Document Intelligence selected OCR; Privacy Decision compared the declared requirements. No inference or cloud calls.

Rehearse the main workflow twice on Windows and twice on the actual presentation Mac if that machine is used. Record the OS-specific checkpoints without inferring one from the other.
