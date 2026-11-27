# PrivacyGate AI — Three-Minute Video Script

Three presenters, approximately one minute each. Timings include short slide changes and speaker handovers. Rehearse at roughly 130–140 words per minute; the script contains approximately 360 spoken words. Only the blockquotes are spoken.

## Presenter allocation

| Presenter | Time | Slides |
|---|---|---|
| Speaker 1 | 0:00–1:00 | 1–3: introduction, problem, solution |
| Speaker 2 | 1:00–2:00 | 4–5: tech stack, architecture |
| Speaker 3 | 2:00–3:00 | 6–8: novelty, feasibility, business model |

## Speaker 1 — Problem and solution

### 0:00–0:10 — Slide 1: Cover

Keep the title visible.

> Hi, we’re presenting PrivacyGate AI, a browser privacy assistant that helps people understand what they share online and where it goes.

### 0:10–0:35 — Slide 2: Problem Statement

Point to the visible-data, hidden-information and recipient sections.

> Uploading a document can reveal more than intended: full ID numbers, contact details, or hidden information such as a PDF author’s name. The file may also reach a separate storage service. Users often need different tools to inspect these details, making informed sharing difficult.

### 0:35–1:00 — Slide 3: Proposed Solution

Follow the three steps, then point to the protected document.

> PrivacyGate combines these checks into one review. Users inspect the findings and intended recipient, then approve selected masking or metadata removal. We create and verify a separate protected copy, preserving the original. Sending the chosen file requires another approval. The preview shows an actual protected synthetic document.

## Speaker 2 — Technology and architecture

### 1:00–1:30 — Slide 4: Tech Stack

Point to the relevant technology groups while speaking.

> We use WXT, React and TypeScript for the Chrome interface, with a local Python and FastAPI backend. PyMuPDF handles PDFs, Tesseract reads scanned text, and Pillow and OpenCV support image processing. LangGraph organises rule-based steps; no language model runs in the current demo. Local processing avoids paid cloud inference. AWS hosting and ElevenLabs voice guidance are optional, planned additions.

### 1:30–2:00 — Slide 5: Process Flow / Architecture Diagram

Trace the solid arrows first; point to the dashed agents last.

> The browser exchanges files, context and results with our local API. Document tools produce findings and verify approved changes. After upload approval, the browser sends the chosen file to the local test recipient, which returns a receipt and discards the body. The expanded workflow currently runs in a local page. Full Chrome integration and the two dashed reasoning agents remain planned.

## Speaker 3 — Differentiation and viability

### 2:00–2:15 — Slide 6: Novelty / Innovation

Point across the comparison table.

> Our contribution is linking document findings, recipient information and approval for a specific file in one workflow. We combine established tools with protection checks and upload evidence, helping users make a clearer sharing decision.

### 2:15–2:40 — Slide 7: Impact & Feasibility

Point to feasibility, impact measurements, risks and expansion.

> We build on an existing Aadhaar-masking and PDF/OCR engine, with local processing reducing cloud costs. Pilots will measure detection accuracy, review time and completion. Uncertain findings need manual review; modifications require approval and preserve originals. Different upload destinations are observations, not automatic threats. We’ll expand formats and website support after testing.

### 2:40–3:00 — Slide 8: Business Model

Keep this slide visible through the closing sentence.

> We propose a freemium extension, Pro subscriptions and future institutional SDK licensing. Student and job-seeker pilots will test usability and willingness to pay before wider partnerships. Costs include maintenance, browser compatibility, security and support. Our goal: know what you’re sharing, and where it’s going.

## Recording notes

- Use slideshow mode and read only the quoted narration.
- Switch presenters at 1:00 and 2:00 without a long introduction.
- Keep the distinction between the working local prototype and planned features clear.
- The receipt is evidence from the controlled local upload; it does not certify an external recipient’s trustworthiness or later handling of a file.
- SDK licensing, Pro subscriptions, AWS, ElevenLabs and the two reasoning agents are proposals, not completed integrations or validated revenue.
- Aim to finish the final sentence at about 2:58 and hold the last slide for two seconds.
