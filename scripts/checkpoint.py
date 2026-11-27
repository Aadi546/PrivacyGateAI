"""Run on each actual target machine; never infer an OS result from another OS."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.ocr import health

parser = argparse.ArgumentParser()
parser.add_argument("--day", choices=("1", "2"), required=True)
args = parser.parse_args()
ocr = health()
result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True)
report = {
    "checkpoint": f"day-{args.day}", "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    "system": platform.system(), "release": platform.release(), "architecture": platform.machine(),
    "python": platform.python_version(), "ocr": ocr,
    "backend_tests_passed": result.returncode == 0, "test_output": result.stdout,
    "browser_checks": "Run and record the manual checklist in docs/platform-checkpoints.md; not inferred from backend tests.",
}
destination = ROOT / "docs" / "checkpoints"
destination.mkdir(parents=True, exist_ok=True)
name = f"{platform.system().lower()}-day-{args.day}.json"
(destination / name).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(result.stdout)
print(f"Recorded {destination / name}")
sys.exit(0 if result.returncode == 0 and ocr.get("available") else 1)
