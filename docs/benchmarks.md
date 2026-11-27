# Three CPU-only demo runs

System: Windows 11 / AMD64; Python 3.13.4.

Fixture: synthetic scanned Aadhaar-like PNG. No model inference calls. Analysis includes QR inspection; output verification includes OCR. These are observed runs, not performance guarantees.

| Run | Analysis (ms) | Redaction + verification (ms) | Total (ms) | Result |
|---|---:|---:|---:|---|
| 1 | 1419 | 587 | 2006 | passed_supported_checks |
| 2 | 918 | 581 | 1499 | passed_supported_checks |
| 3 | 944 | 599 | 1543 | passed_supported_checks |
