"""Package source, synthetic fixtures, and built extension, never local environments."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "artifacts" / "PrivacyGate-AI-prototype.zip"
EXCLUDED = {"node_modules", ".git", ".wxt", "__pycache__", ".pytest_cache", ".venv", ".runtime", ".aws", ".codex", ".agents", ".openai", ".env", ".env.local", ".env.production", ".env.development", "approved-plan.md", "checkpoints"}
DIRECTORIES = ("backend", "chrome-extension", "prototype", "sample-documents", "tests", "scripts", "docs")
ROOT_FILES = ("README.md", "requirements.txt", "setup.ps1", "setup.sh", "start.ps1", "start.sh", "start-practical.ps1", "start-practical.sh", ".gitignore")

if not (ROOT / "chrome-extension/.output/chrome-mv3/manifest.json").is_file():
    raise SystemExit("Build the extension before packaging.")
files = [ROOT / name for name in ROOT_FILES]
for directory in DIRECTORIES:
    files.extend(path for path in (ROOT / directory).rglob("*") if path.is_file() and not EXCLUDED.intersection(path.relative_to(ROOT).parts) and not path.name.startswith(".env") and path.suffix not in {".log", ".pyc", ".pem", ".key", ".p12", ".pfx"})
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted(files):
        archive.write(path, "PrivacyGate-AI/" + path.relative_to(ROOT).as_posix())
with ZipFile(OUTPUT) as archive:
    assert archive.testzip() is None
    assert not any(EXCLUDED.intersection(Path(name).parts) for name in archive.namelist())
print(f"Packaged {len(files)} files: {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
