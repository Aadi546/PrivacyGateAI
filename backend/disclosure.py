"""Practical local disclosure inspection and single-use, loopback upload receipts."""

import hashlib
import secrets
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Literal

import fitz
from PIL import Image, ImageDraw, ExifTags
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, StrictBool

from . import engine, ocr, comparison
from .fixtures import make_fixture

ORIGINS = {"http://127.0.0.1:8765", "http://localhost:8765"}
GRANTS = {}
GRANT_LOCK = threading.RLock()
GRANT_TTL = 90
SAMPLES = {
    "identity": ("identity-with-metadata.pdf", "Identity PDF + author metadata"),
    "scan": ("scanned-identity.png", "Scanned identity image / real OCR"),
    "photo": ("photo-with-exif.jpg", "JPEG with synthetic EXIF"),
    "clean": ("enrolment-confirmation.pdf", "Clean enrolment document"),
    "signed": ("signature-indicator.pdf", "Signature indicator / changes blocked"),
    "bank": ("fictional-bank-statement.pdf", "Fictional bank statement"),
    "utility": ("fictional-electricity-bill.pdf", "Fictional electricity bill"),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def metadata(data):
    findings = []
    if data.startswith(b"%PDF-"):
        with fitz.open(stream=data, filetype="pdf") as doc:
            for key in ("author", "creator", "producer", "title", "subject", "keywords", "creationDate", "modDate"):
                value = (doc.metadata or {}).get(key)
                if value:
                    findings.append({"id": "pdf." + key, "label": "PDF " + key, "evidence": f"Property present ({len(value)} characters)", "kind": "PDF metadata"})
            if doc.get_xml_metadata():
                findings.append({"id": "pdf.xmp", "label": "PDF XMP packet", "evidence": "XML metadata packet present", "kind": "PDF metadata"})
        coverage = "Standard PDF properties and XMP presence; not exhaustive hidden-content inspection."
    else:
        with Image.open(BytesIO(data)) as image:
            for tag in image.getexif():
                name = ExifTags.TAGS.get(tag, str(tag))
                findings.append({"id": "exif." + str(tag), "label": "EXIF " + name, "evidence": "GPS fields present" if tag == 34853 else "Metadata field present", "kind": "Image metadata"})
            for key in ("XML:com.adobe.xmp", "xmp", "Comment", "comment", "Description", "Author"):
                if image.info.get(key):
                    findings.append({"id": "image." + key, "label": "Image " + key, "evidence": "Ancillary metadata present", "kind": "Image metadata"})
        coverage = "Readable EXIF tags and selected ancillary fields; not exhaustive image metadata inspection."
    return {"findings": findings, "coverage": coverage, "status": "completed_supported_checks"}


def sample(kind):
    if kind not in SAMPLES:
        raise HTTPException(404, "Sample not found.")
    if kind in ("bank", "utility"):
        common = ["PRIVACYGATE / FICTIONAL DEMONSTRATION ONLY", "NOT VALID AS ADDRESS PROOF",
                  "Bank statement" if kind == "bank" else "Electricity bill", "Name: Alex Sample",
                  "Address: 14 Cedar Lane, Bengaluru 560001", "Statement date: 2026-11-20"]
        content = (["Account number: 112233445566", "Opening balance: INR 42,000.00",
                    "Closing balance: INR 40,750.00", "Date  Description  Debit  Credit",
                    "2026-11-01  Metro Market  1,250.00  0.00", "2026-11-03  Salary  0.00  35,000.00",
                    "Phone: 9876543210", "Email: alex.sample@example.com"] if kind == "bank" else
                   ["Consumer ID: EL-730042", "Units consumed: 120 kWh", "Amount due: INR 840.00",
                    "Due date: 2026-12-05", "Email: alex.sample@example.com"])
        with fitz.open() as doc:
            page = doc.new_page(width=620, height=550)
            for index, line in enumerate(common + [""] + content):
                page.insert_text((40, 40 + index * 25), line, fontsize=12 if index != 2 else 22)
            doc.set_metadata({"author": "Fictional demonstration team", "title": SAMPLES[kind][1]})
            return doc.tobytes(garbage=4), "application/pdf"
    if kind == "scan":
        return make_fixture("aadhaar-scan.png"), "image/png"
    if kind == "signed":
        return make_fixture("signature-indicator.pdf"), "application/pdf"
    if kind == "photo":
        image = Image.new("RGB", (1000, 700), "#eee8f5")
        draw = ImageDraw.Draw(image)
        draw.rectangle((80, 80, 920, 620), fill="white")
        draw.text((125, 125), "PRIVACYGATE SYNTHETIC PHOTO - NOT A REAL LOCATION", fill="#594277", font_size=24)
        draw.text((125, 205), "A harmless-looking image can carry metadata.", fill="#594277", font_size=24)
        exif = Image.Exif()
        exif[271] = "PrivacyGate Fictional Camera"
        exif[272] = "Synthetic Model 01"
        exif[306] = "2026:11:24 12:00:00"
        exif[34853] = {1: "N", 2: (0.0, 0.0, 0.0), 3: "E", 4: (0.0, 0.0, 0.0)}
        out = BytesIO()
        image.save(out, format="JPEG", exif=exif)
        return out.getvalue(), "image/jpeg"
    if kind == "clean":
        with fitz.open() as doc:
            page = doc.new_page(width=620, height=400)
            page.insert_text((45, 55), "PRIVACYGATE / FICTIONAL SAMPLE", fontsize=15)
            page.insert_text((45, 110), "Enrolment confirmation", fontsize=25)
            page.insert_text((45, 155), "Alex Sample is enrolled in a fictional course.", fontsize=15)
            page.insert_text((45, 225), "NOT VALID FOR OFFICIAL USE", fontsize=13)
            doc.set_metadata({})
            return doc.tobytes(garbage=4), "application/pdf"
    data = engine.sample_document()
    with fitz.open(stream=data, filetype="pdf") as doc:
        doc.set_metadata({"author": "Sample Applicant", "creator": "Fictional campus scanner", "title": "Synthetic identity proof"})
        return doc.tobytes(garbage=4), "application/pdf"


def sanitize(data, report):
    if report["authentication"]["signature_indicator"]:
        raise engine.InputError("Signature indicator detected. All modification is blocked.")
    if any("Unsupported PDF structures" in item for item in report["limitations"]):
        raise engine.InputError("This file contains structures that cannot be safely sanitised by the prototype.")
    if data.startswith(b"%PDF-"):
        with fitz.open(stream=data, filetype="pdf") as doc:
            doc.set_metadata({})
            if doc.get_xml_metadata():
                doc.del_xml_metadata()
            return doc.tobytes(garbage=4, deflate=True), "application/pdf"
    with Image.open(BytesIO(data)) as image:
        fresh = ocr.clean_image(image)
        out = BytesIO()
        fresh.save(out, format="PNG")
        return out.getvalue(), "image/png"


class Protection(BaseModel):
    finding_ids: list[str] = Field(default_factory=list, max_length=100)
    remove_metadata: bool
    approved: bool


class Context(BaseModel):
    page_origin: Literal["http://127.0.0.1:8765", "http://localhost:8765"] = "http://127.0.0.1:8765"
    mode: Literal["same_origin", "cross_origin"] = "cross_origin"


class Submission(Context):
    variant: Literal["original", "output"]
    approved: bool


class ComparisonCandidate(BaseModel):
    model_config = {"extra": "forbid"}
    session_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    acceptance: Literal["accepted", "not_accepted", "unknown"] = "unknown"
    required_details_confirmed: StrictBool = False


class ComparisonRequest(BaseModel):
    model_config = {"extra": "forbid"}
    candidates: list[ComparisonCandidate] = Field(min_length=2, max_length=2)


def recipient(context):
    target = context.page_origin if context.mode == "same_origin" else "http://127.0.0.1:8766"
    return {"page_origin": context.page_origin, "declared_destination": target + "/mock-upload", "observed_destination": None,
            "origin_comparison": "same_origin" if target == context.page_origin else "cross_origin",
            "relationship": "Configured local demo recipient", "evidence_source": "Controlled portal configuration; request observation pending", "receipt": None}


def invalidate_grants(session_id):
    with GRANT_LOCK:
        for key, value in list(GRANTS.items()):
            if value["session_id"] == session_id or value["expires"] < time.monotonic():
                GRANTS.pop(key, None)


def output_ready(session):
    proof = session.report.get("practical_verification", {})
    pii_checks = proof.get("checks", [])
    pii_ok = (not proof.get("pii_requested") and proof.get("metadata_requested") is True) or (
        bool(pii_checks) and all(c.get("removed") is True and c.get("replacement_rendered") is True for c in pii_checks))
    return bool(session.output and proof.get("status") == "passed_supported_checks" and pii_ok
                and proof.get("metadata_removed") is True and proof.get("technical_compatibility") is True
                and proof.get("original_unchanged") is True and proof.get("output_digest") == digest(session.output))


def install(app, sessions, session_for, lock, processing, root):
    @app.get("/practical")
    def practical():
        return FileResponse(root / "prototype" / "practical" / "index.html")

    @app.get("/api/practical/samples/{kind}")
    def fixture(kind: str):
        data, mime = sample(kind)
        return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{SAMPLES[kind][0]}"'})

    def clear_output(session_id, session):
        invalidate_grants(session_id)
        session.output = None
        session.verification = None
        session.report.pop("practical_verification", None)
        if session.report.get("recipient"):
            session.report["recipient"]["observed_destination"] = None
            session.report["recipient"]["receipt"] = None
            session.report["recipient"]["evidence_source"] = "Controlled portal configuration; request observation pending"

    @app.post("/api/practical/compare")
    def compare_documents(request: ComparisonRequest):
        if request.candidates[0].session_id == request.candidates[1].session_id:
            raise HTTPException(422, "Choose two different inspection sessions.")
        if not processing.acquire(blocking=False):
            raise HTTPException(409, "Another document is processing. Retry the comparison shortly.")
        try:
            with lock:
                resolved = [(item, session_for(item.session_id)) for item in request.candidates]
                summaries = []
                for item, session in resolved:
                    hidden = metadata(session.original)
                    summaries.append(comparison.summarize(item.session_id, session.report, hidden,
                                                         item.acceptance, item.required_details_confirmed))
                for item, session in resolved:
                    clear_output(item.session_id, session)
                return comparison.compare(summaries)
        finally:
            processing.release()

    @app.post("/api/practical/sessions/{session_id}/clear-protection")
    def clear_protection(session_id: str):
        if not processing.acquire(blocking=False):
            raise HTTPException(409, "Another document is processing. Retry shortly.")
        try:
            with lock:
                clear_output(session_id, session_for(session_id))
            return {"cleared": True}
        finally:
            processing.release()

    @app.post("/api/practical/sessions/{session_id}/context")
    def set_context(session_id: str, context: Context):
        with lock:
            session = session_for(session_id)
            if "hidden_information" not in session.report:
                session.report["hidden_information"] = metadata(session.original)
            session.report["recipient"] = recipient(context)
            invalidate_grants(session_id)
            return {"hidden_information": session.report["hidden_information"], "recipient": session.report["recipient"],
                    "original_digest": digest(session.original), "processing": "local_deterministic"}

    @app.post("/api/practical/sessions/{session_id}/protect")
    def protect(session_id: str, approval: Protection):
        if not approval.approved or not approval.remove_metadata:
            raise HTTPException(400, "Approve the complete transformation: selected masks and supported metadata removal.")
        if not processing.acquire(blocking=False):
            raise HTTPException(409, "Another document is processing.")
        try:
            session = session_for(session_id)
            invalidate_grants(session_id)
            session.output = None
            session.verification = None
            session.report.pop("practical_verification", None)
            if session.report["authentication"]["signature_indicator"]:
                raise engine.InputError("Signature indicator detected. All modification is blocked.")
            original_digest = digest(session.original)
            start = time.perf_counter()
            if approval.finding_ids:
                output, verification = engine.redact(session.original, session.report, approval.finding_ids)
                mime = verification["mime"]
            else:
                if not metadata(session.original)["findings"]:
                    raise engine.InputError("No selected changes. Continue with the original instead.")
                output, mime = sanitize(session.original, session.report)
                verification = {"status": "passed_supported_checks", "checks": []}
            hidden_after = metadata(output)
            meta_ok = not hidden_after["findings"]
            output_format = "pdf" if mime == "application/pdf" else "png"
            rules = session.report["compatibility"]
            technical = len(output) <= rules["max_bytes"] and output_format in rules["accepted_formats"]
            passed = verification["status"] == "passed_supported_checks" and meta_ok and technical and digest(session.original) == original_digest
            proof = {**verification, "status": "passed_supported_checks" if passed else "failed", "metadata_removed": meta_ok,
                     "metadata_requested": True, "pii_requested": bool(approval.finding_ids), "original_unchanged": digest(session.original) == original_digest,
                     "mime": mime, "technical_compatibility": technical, "output_size": len(output), "output_digest": digest(output),
                     "elapsed_ms": round((time.perf_counter() - start) * 1000), "hidden_after": hidden_after,
                     "limitations": "Supported target-removal and metadata checks only. No anonymity, authenticity or recipient-acceptance guarantee."}
            session.output = output
            session.verification = verification
            session.report["practical_verification"] = proof
            return {"verification": proof}
        finally:
            processing.release()

    @app.get("/api/practical/sessions/{session_id}/download")
    def download(session_id: str):
        session = session_for(session_id)
        if not output_ready(session):
            raise HTTPException(409, "Protected output is unavailable until all required checks pass.")
        mime = session.report["practical_verification"]["mime"]
        extension = ".pdf" if mime == "application/pdf" else ".png"
        return Response(session.output, media_type=mime, headers={"Content-Disposition": 'attachment; filename="privacygate-protected' + extension + '"'})

    @app.post("/api/practical/sessions/{session_id}/upload-approval")
    def approve_upload(session_id: str, approval: Submission):
        if not approval.approved:
            raise HTTPException(400, "Separate submission approval is required.")
        with lock:
            session = session_for(session_id)
            if approval.variant == "output" and not output_ready(session):
                raise HTTPException(409, "Protected copy has not passed required checks.")
            if not session.report["compatibility"]["size_ok"] or not session.report["compatibility"]["format_ok"]:
                raise HTTPException(409, "Input does not meet the controlled portal requirements.")
            current = recipient(approval)
            session.report["recipient"] = current
            data = session.output if approval.variant == "output" else session.original
            invalidate_grants(session_id)
            grant = secrets.token_urlsafe(32)
            upload_id = secrets.token_hex(8)
            with GRANT_LOCK:
                GRANTS[grant] = {"session_id": session_id, "expires": time.monotonic() + GRANT_TTL, "digest": digest(data), "bytes": len(data),
                                 "url": current["declared_destination"], "origin": approval.page_origin, "upload_id": upload_id, "variant": approval.variant}
            return {"grant": grant, "upload_id": upload_id, "upload_url": current["declared_destination"], "expires_in_seconds": GRANT_TTL}

    async def receive(request: Request):
        origin = request.headers.get("origin")
        if origin not in ORIGINS:
            raise HTTPException(403, "Unexpected upload origin.")
        grant = request.headers.get("x-privacygate-upload-grant", "")
        with GRANT_LOCK:
            record = GRANTS.pop(grant, None)
        if not record or record["expires"] < time.monotonic():
            raise HTTPException(403, "Upload approval is missing, expired or already used.")
        if str(request.url) != record["url"] or origin != record["origin"]:
            raise HTTPException(403, "Upload destination does not match the approved recipient.")
        count, sha = 0, hashlib.sha256()
        async for chunk in request.stream():
            count += len(chunk)
            if count > engine.MAX_BYTES:
                raise HTTPException(413, "Upload exceeds the processing limit.")
            sha.update(chunk)
        if count != record["bytes"] or sha.hexdigest() != record["digest"]:
            raise HTTPException(400, "Uploaded bytes do not match the approved file.")
        session = session_for(record["session_id"])
        if record["variant"] == "output" and not output_ready(session):
            raise HTTPException(409, "Protected output is no longer valid.")
        receipt = {"upload_id": record["upload_id"], "destination": str(request.url), "method": request.method,
                   "bytes_received": count, "matching_approved_file": True, "body_retained": False,
                   "correlation_status": "matched_controlled_session", "evidence_source": "Controlled portal request and local receiver receipt"}
        with lock:
            session.report["recipient"]["observed_destination"] = str(request.url)
            session.report["recipient"]["receipt"] = receipt
            session.report["recipient"]["evidence_source"] = receipt["evidence_source"]
        return JSONResponse(receipt, headers={"Cache-Control": "no-store"})

    app.add_api_route("/mock-upload", receive, methods=["POST"])
    receiver = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @receiver.middleware("http")
    async def receiver_security(request: Request, call_next):
        origin = request.headers.get("origin", "")
        if request.headers.get("host") != "127.0.0.1:8766" or origin not in ORIGINS:
            return JSONResponse({"detail": "Unexpected receiver host or origin."}, status_code=403)
        if request.method == "OPTIONS":
            response = Response(status_code=204)
        else:
            response = await call_next(request)
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-PrivacyGate-Upload-Grant"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    receiver.add_api_route("/mock-upload", receive, methods=["POST"])
    return receiver
