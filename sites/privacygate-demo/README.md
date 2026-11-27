# PrivacyGate guided demo

A standalone concept walkthrough using synthetic scenario data. No real documents are accepted, no AI model or inspection engine is called, and no upload request is performed. All state lives in browser memory.

Serve `dist/` with any static server. For example: `python -m http.server 4173 --bind 127.0.0.1 --directory dist`.

Run the approval/state-transition checks with `node --test scenario.test.mjs`.

Scenarios cover an identity document with metadata and a separate storage origin, a clean document, and a document with signature/QR indicators. The separate masking backend and Chrome extension are unchanged.

For the complete walkthrough: choose the identity sample, inspect it, select changes, approve them, compare copies, separately approve submission, and observe the updated simulated recipient report.
