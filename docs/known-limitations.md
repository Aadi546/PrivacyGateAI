# Known limitations

- Prototype intended for single-page synthetic documents and a single controlled portal. Multi-page, encrypted, corrupted, interactive-form, annotation/link, or attachment-heavy PDFs fail safely or remain blocked.
- English OCR and pattern matching may miss or misread PII. A missing match is not proof of safety. Unreliable character boundaries cannot be manually overridden; use a clearer sample.
- Verhoeff validity is a confidence signal, not proof of a valid Aadhaar. Fixtures are fictional and visibly labeled as demos.
- QR detection checks indicators only. QR payloads remain unchanged and can retain identifying information. Prefer an official masked document where relevant.
- Signature detection checks structural indicators, not cryptographic authenticity. Any indicator blocks modification, even if the PDF is not genuinely signed.
- Native PDF verification covers supported searchable text and the inserted readable masks at their intended locations. Raster verification compares approved regions to the deterministic rendered mask, checks retained Aadhaar last-four pixels, and re-runs OCR. Passing does not certify complete anonymity or recipient acceptance.
- Clean readable masking requires a reliably uniform surrounding background. Textured, patterned, or uncertain backgrounds block output with a limitation. The bundled Helvetica font gives consistent Windows/macOS results but does not reproduce every original typeface exactly.
- A nearby border may contaminate one background-sampling edge without blocking masking: three edges must agree, padding stops before neighboring content, and the text area is checked separately. Lines or colored patterns crossing that area remain unsupported.
- Partial phone, PAN, and email masks intentionally retain the last four phone digits, first/last two PAN characters, and first email character/domain, as shown in the finding. Approve only the partial disclosures you intend to share.
- Photos/images are exported as fresh PNGs. If the recipient only accepts JPEG, verification fails for the PNG output. No automatic conversion/compression strategy is added.
- Raster PDF redaction intentionally reconstructs the page and removes its original searchable text layer. Visual content outside approved regions is preserved within the renderer's supported behavior.
- The mock portal validates file signature and size in the browser. Its submission is simulated; it does not independently verify identity or parse PDF page count.
- Closing the side panel does not reliably notify a service worker on every Chrome lifecycle transition. Explicit Clear deletes a session immediately; abandoned sessions expire within 15 minutes, with periodic cleanup. Tesseract temporary files are removed at each call's completion, including handled errors.
- A process or person already controlling the local computer is outside the prototype's protection boundary. The pairing token is a local session credential, not a cloud login.
- Windows runtime checks are recorded here. The owner's friend performs actual macOS runtime checkpoints on his Mac; pending results are never reported as passed.
- No local LLM, cloud processing, manual redaction regions, general requirement scraping, universal upload interception, automatic upload, or paid API.
