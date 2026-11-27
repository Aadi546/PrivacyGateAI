"""Record synthetic, actual-machine practical API timings without document values."""
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.main import app, SESSIONS, TOKEN
from backend.disclosure import sample, SAMPLES

runs = []
with TestClient(app, base_url="http://127.0.0.1:8765") as client:
    headers = {"X-PrivacyGate-Token": TOKEN}
    for kind in ("identity", "scan"):
        for run in range(1, 4):
            SESSIONS.clear()
            data, mime = sample(kind)
            start = time.perf_counter()
            response = client.post("/api/analyze", headers=headers, files={"file": (SAMPLES[kind][0], data, mime)})
            response.raise_for_status()
            report = response.json()
            sid = report["session_id"]
            context = client.post(f"/api/practical/sessions/{sid}/context", headers=headers, json={"mode": "cross_origin"})
            context.raise_for_status()
            protection = client.post(f"/api/practical/sessions/{sid}/protect", headers=headers,
                                     json={"finding_ids": [f["id"] for f in report["findings"]], "remove_metadata": True, "approved": True})
            protection.raise_for_status()
            proof = protection.json()["verification"]
            download = client.get(f"/api/practical/sessions/{sid}/download", headers=headers)
            download.raise_for_status()
            runs.append({"sample": kind, "run": run, "analysis_ms": report["elapsed_ms"], "protection_verification_ms": proof["elapsed_ms"],
                         "api_pipeline_ms": round((time.perf_counter()-start)*1000), "metadata_removed": proof["metadata_removed"],
                         "status": proof["status"], "output_bytes": len(download.content)})
result = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(), "python": platform.python_version(),
          "scope": "Synthetic local API analysis, metadata inspection, protection, verification and download. No browser rendering, user decision or network upload time. No LLM calls.", "runs": runs}
path = ROOT / "docs" / "practical-benchmarks.json"
path.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
print(json.dumps(result, indent=2))
