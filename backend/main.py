"""Loopback-only web prototype; document bytes remain in process memory."""

import asyncio
import json
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import engine, ocr
from .fixtures import FIXTURES, make_fixture

ROOT = Path(__file__).resolve().parent.parent
TOKEN = secrets.token_urlsafe(32)
TTL = 15 * 60
ALLOWED_ORIGINS = {"http://127.0.0.1:8765", "http://localhost:8765"}
identity_path = ROOT / "chrome-extension" / "extension-identity.json"
if identity_path.is_file():
    ALLOWED_ORIGINS.add("chrome-extension://" + json.loads(identity_path.read_text(encoding="utf-8"))["extension_id"])
SESSIONS = {}
PROCESSING = threading.Lock()
SESSION_LOCK = threading.RLock()


@dataclass
class Session:
    original: bytes
    report: dict
    touched: float
    output: bytes | None = None
    verification: dict | None = None


def expire():
    with SESSION_LOCK:
        expired = [key for key, session in SESSIONS.items() if time.monotonic() - session.touched > TTL]
        for key in expired:
            del SESSIONS[key]


async def cleanup():
    while True:
        await asyncio.sleep(60)
        expire()


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(cleanup())
    yield
    task.cancel()
    with SESSION_LOCK:
        SESSIONS.clear()


app = FastAPI(title="PrivacyGate AI local prototype", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def local_security(request: Request, call_next):
    host = request.headers.get("host", "")
    if host not in {"127.0.0.1:8765", "localhost:8765"}:
        return JSONResponse({"detail": "Invalid local host."}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse({"detail": "Unexpected origin."}, status_code=403)
    if request.url.path.startswith("/api/") or request.url.path == "/health":
        if not secrets.compare_digest(request.headers.get("x-privacygate-token", ""), TOKEN):
            return JSONResponse({"detail": "Pair with the token printed in your local backend terminal."}, status_code=401)
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > engine.MAX_BYTES + 65536):
        return JSONResponse({"detail": "Request exceeds the 10 MB processing limit."}, status_code=413)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self' http://127.0.0.1:8766; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    return response


@app.exception_handler(engine.InputError)
async def input_error(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.exception_handler(Exception)
async def unknown_error(request, exc):
    # Never include source document data or exception values in the response.
    return JSONResponse({"detail": "Processing failed. Choose a supported, clear single-page synthetic document."}, status_code=500)


@app.get("/health")
def health():
    return {"status": "ok", "processing": "local", "pdf": True, "ocr": ocr.health(), "llm": False, "qr_detection": True}


def session_for(session_id):
    expire()
    with SESSION_LOCK:
        session = SESSIONS.get(session_id)
        if session is None:
            raise HTTPException(404, "Session expired or was cleared. Inspect the file again.")
        session.touched = time.monotonic()
        return session


def parse_requirements(raw):
    try:
        requirements = json.loads(raw)
        if not isinstance(requirements, dict):
            raise ValueError()
        max_bytes = int(requirements.get("max_bytes", 2 * 1024 * 1024))
        formats = requirements.get("formats", ["pdf", "png", "jpeg"])
        fields = requirements.get("required_fields", [])
        if not 1 <= max_bytes <= 10 * 1024 * 1024:
            raise ValueError()
        if not isinstance(formats, list) or not formats or not all(item in ("pdf", "jpeg", "png") for item in formats):
            raise ValueError()
        if not isinstance(fields, list) or not all(item in engine.PATTERNS for item in fields):
            raise ValueError()
        return {"max_bytes": max_bytes, "formats": formats, "required_fields": fields, "source": "User-reviewed demo portal requirements"}
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise engine.InputError("Upload requirements are invalid. Reset the portal settings and try again.") from exc


@app.post("/api/analyze")
def analyze(file: UploadFile = File(...), requirements: str = Form("{}")):
    rules = parse_requirements(requirements)
    if not PROCESSING.acquire(blocking=False):
        raise HTTPException(409, "Another document is processing. Please try again shortly.")
    try:
        expire()
        with SESSION_LOCK:
            if len(SESSIONS) >= 4:
                raise HTTPException(409, "Four sessions are open. Clear an inspection or wait for expiry.")
        data = file.file.read(engine.MAX_BYTES + 1)
        filename = re.split(r"[\\/]", file.filename or "document.pdf")[-1][:150]
        report = engine.analyze(data, filename, rules)
        session_id = secrets.token_urlsafe(24)
        with SESSION_LOCK:
            SESSIONS[session_id] = Session(data, report, time.monotonic())
        return {"session_id": session_id, **engine.public_report(report)}
    finally:
        file.file.close()
        PROCESSING.release()


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session = session_for(session_id)
    return {"session_id": session_id, **engine.public_report(session.report), "verification": session.verification}


class Approval(BaseModel):
    finding_ids: list[str] = Field(min_length=1, max_length=100)
    approved: bool


@app.post("/api/sessions/{session_id}/redact")
def redact(session_id: str, approval: Approval):
    if not approval.approved:
        raise HTTPException(400, "Explicit approval is required before modification.")
    if not PROCESSING.acquire(blocking=False):
        raise HTTPException(409, "Another document is processing. Please try again shortly.")
    try:
        session = session_for(session_id)
        # Any new attempt invalidates a previous output immediately.
        session.output = None
        session.verification = None
        output, verification = engine.redact(session.original, session.report, approval.finding_ids)
        session.output = output
        session.verification = verification
        return {"verification": verification}
    finally:
        PROCESSING.release()


@app.get("/api/sessions/{session_id}/preview/{page}")
def preview(session_id: str, page: int, variant: str = "original"):
    session = session_for(session_id)
    if variant not in ("original", "output"):
        raise HTTPException(422, "Unknown preview variant.")
    data = session.original if variant == "original" else session.output
    if data is None:
        raise HTTPException(404, "No protected output exists yet.")
    return Response(engine.preview(data, page), media_type="image/png")


@app.get("/api/sessions/{session_id}/download")
def download(session_id: str):
    session = session_for(session_id)
    if (not session.output or not session.verification or session.verification["status"] != "passed_supported_checks"
            or not session.verification.get("checks")
            or not all(check.get("removed") and check.get("replacement_rendered") for check in session.verification["checks"])):
        raise HTTPException(409, "Download is blocked until supported redaction checks pass.")
    stem = Path(re.sub(r"[^A-Za-z0-9._-]", "_", session.report["filename"])).stem
    mime = session.verification["mime"]
    filename = "protected-" + stem + (".pdf" if mime == "application/pdf" else ".png")
    return Response(session.output, media_type=mime, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    with SESSION_LOCK:
        SESSIONS.pop(session_id, None)
    return {"deleted": True}


@app.get("/api/sample/{kind}")
def sample(kind: str):
    if kind not in FIXTURES:
        raise HTTPException(404, "Sample not found.")
    mime = "application/pdf" if kind.endswith(".pdf") else "image/png"
    return Response(make_fixture(kind), media_type=mime, headers={"Content-Disposition": f'attachment; filename="{kind}"'})


@app.get("/")
def home():
    build = ROOT / "chrome-extension" / ".output" / "chrome-mv3" / "sidepanel.html"
    if not build.is_file():
        return Response("Build the extension first: cd chrome-extension && npm install && npm run build", media_type="text/plain", status_code=503)
    return FileResponse(build)


@app.get("/portal")
def portal():
    return FileResponse(ROOT / "prototype" / "portal.html")


app.mount("/static", StaticFiles(directory=ROOT / "prototype"), name="static")
app.mount("/fixtures", StaticFiles(directory=ROOT / "sample-documents"), name="fixtures")
app.mount("/chunks", StaticFiles(directory=ROOT / "chrome-extension" / ".output" / "chrome-mv3" / "chunks", check_dir=False), name="extension-chunks")
app.mount("/assets", StaticFiles(directory=ROOT / "chrome-extension" / ".output" / "chrome-mv3" / "assets", check_dir=False), name="extension-assets")

# Additive practical APIs; the existing extension API remains compatible.
from .disclosure import install as install_disclosure
receiver_app = install_disclosure(app, SESSIONS, session_for, SESSION_LOCK, PROCESSING, ROOT)
