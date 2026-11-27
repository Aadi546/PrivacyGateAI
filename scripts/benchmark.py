"""Exactly three timed synthetic CPU runs, without identifiers in the output."""

from pathlib import Path
import platform
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import engine
from backend.fixtures import make_fixture

data = make_fixture("aadhaar-scan.png")
rules = {"formats": ["png", "pdf", "jpeg"], "max_bytes": 2097152, "required_fields": []}
rows = []
for run in range(1, 4):
    started = perf_counter()
    report = engine.analyze(data, "synthetic.png", rules)
    analyzed = perf_counter()
    approved = [finding["id"] for finding in report["findings"] if finding["category"] == "aadhaar"]
    _, result = engine.redact(data, report, approved)
    ended = perf_counter()
    rows.append(f"| {run} | {(analyzed-started)*1000:.0f} | {(ended-analyzed)*1000:.0f} | {(ended-started)*1000:.0f} | {result['status']} |")
text = f"# Three CPU-only demo runs\n\nSystem: {platform.system()} {platform.release()} / {platform.machine()}; Python {platform.python_version()}.\n\nFixture: synthetic scanned Aadhaar-like PNG. No model inference calls. Analysis includes QR inspection; output verification includes OCR. These are observed runs, not performance guarantees.\n\n| Run | Analysis (ms) | Redaction + verification (ms) | Total (ms) | Result |\n|---|---:|---:|---:|---|\n" + "\n".join(rows) + "\n"
destination = ROOT / "docs" / "benchmarks.md"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(text, encoding="utf-8")
print(text)
