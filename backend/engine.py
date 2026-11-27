"""Bounded local document analysis. Never call external services."""

import re
from io import BytesIO
from time import perf_counter
from typing import TypedDict

import fitz
from PIL import Image, ImageChops
from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from . import ocr, masking, comparison

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 1
MAX_PIXELS = 20_000_000
PATTERNS = {
    "aadhaar": re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)"),
    "pan": re.compile(r"(?<![A-Z0-9])[A-Z]{5}\d{4}[A-Z](?![A-Z0-9])", re.I),
    "email": re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I),
    "phone": re.compile(r"(?<!\d)(?:\+91[ -]?)?[6-9]\d{9}(?!\d)"),
}
LABELS = {"aadhaar": "Aadhaar number", "pan": "PAN number", "email": "Email address", "phone": "Phone number"}
VERHOEFF_D = ((0,1,2,3,4,5,6,7,8,9),(1,2,3,4,0,6,7,8,9,5),(2,3,4,0,1,7,8,9,5,6),(3,4,0,1,2,8,9,5,6,7),(4,0,1,2,3,9,5,6,7,8),(5,9,8,7,6,0,4,3,2,1),(6,5,9,8,7,1,0,4,3,2),(7,6,5,9,8,2,1,0,4,3),(8,7,6,5,9,3,2,1,0,4),(9,8,7,6,5,4,3,2,1,0))
VERHOEFF_P = ((0,1,2,3,4,5,6,7,8,9),(1,5,7,6,2,8,3,0,9,4),(5,8,0,3,7,9,6,1,4,2),(8,9,1,6,0,4,3,5,2,7),(9,4,5,3,1,2,6,8,7,0),(4,2,8,6,5,7,3,9,0,1),(2,7,9,3,8,0,6,4,1,5),(7,0,4,6,9,1,3,2,5,8))


def verhoeff_valid(value):
    digits = re.sub(r"\D", "", value)
    if len(digits) != 12:
        return False
    result = 0
    for index, digit in enumerate(reversed(digits)):
        result = VERHOEFF_D[result][VERHOEFF_P[index % 8][int(digit)]]
    return result == 0


class InputError(ValueError):
    pass


class GraphState(TypedDict, total=False):
    data: bytes
    filename: str
    requirements: dict
    kind: str
    extracted: dict
    report: dict
    trace: list


def normalize(value):
    return re.sub(r"\s+|-", "", value).lower()


def mask(kind, value):
    if kind == "aadhaar":
        return "xxxx xxxx " + re.sub(r"\D", "", value)[-4:]
    if kind == "phone":
        digits = re.sub(r"\D", "", value)
        return "x" * (len(digits) - 4) + digits[-4:]
    if kind == "pan":
        return value[:2] + "xxxxxx" + value[-2:]
    local, domain = value.split("@", 1)
    return local[:1] + "***@" + domain


def inspect_file(state):
    data = state["data"]
    if not data or len(data) > MAX_BYTES:
        raise InputError("Choose a non-empty file smaller than 10 MB.")
    if data.startswith(b"%PDF-"):
        kind = "pdf"
    elif data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff"):
        kind = "image"
    else:
        raise InputError("Unsupported file. This prototype accepts PDF, JPEG, and PNG.")
    return {"kind": kind, "trace": [{"agent": "Document Intelligence", "tool": "Inspect file", "detail": "Validated file signature and processing size limit."}]}


def extract_pdf(state):
    try:
        doc = fitz.open(stream=state["data"], filetype="pdf")
    except Exception as exc:
        raise InputError("This PDF is corrupted or cannot be opened.") from exc
    with doc:
        if doc.needs_pass:
            raise InputError("Encrypted PDFs are not supported. Choose an unencrypted copy.")
        if len(doc) != 1:
            raise InputError("This prototype supports single-page documents only.")
        lines, signed, risky, has_images = [], False, [], False
        for page in doc:
            if page.rect.width <= 0 or page.rect.height <= 0 or page.rect.width * page.rect.height * 4 > MAX_PIXELS:
                raise InputError("A PDF page exceeds the supported preview dimensions.")
            widgets = list(page.widgets() or [])
            signed = signed or any(w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE for w in widgets)
            if widgets:
                risky.append("Interactive form fields")
            if list(page.annots() or []) or page.get_links():
                risky.append("Annotations or links")
            if page.get_images():
                has_images = True
            raw = page.get_text("rawdict")
            for block in raw.get("blocks", []):
                for line in block.get("lines", []):
                    chars = [{**char, "font_size": span["size"], "font_color": span["color"]}
                             for span in line.get("spans", []) for char in span.get("chars", [])]
                    text = "".join(char["c"] for char in chars)
                    if text.strip():
                        lines.append({"page": page.number, "text": text, "chars": chars, "width": page.rect.width, "height": page.rect.height})
        if doc.embfile_count():
            risky.append("Embedded attachments")
        # Signature presence is an indicator, never a cryptographic verification.
        for xref in range(1, doc.xref_length()):
            obj = doc.xref_object(xref)
            if re.search(r"/ByteRange\b|/(?:Type|FT)\s*/Sig\b|/SigFlags\s+[1-9]\d*", obj):
                signed = True
        text_available = any(line["text"].strip() for line in lines)
        limitations = []
        processing_path = "pdf_raster" if has_images or not text_available else "pdf_text"
        rendered = Image.open(BytesIO(doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes("png"))).convert("RGB")
        if rendered.width * rendered.height > MAX_PIXELS:
            raise InputError("PDF page exceeds the supported rendering dimensions.")
        if processing_path == "pdf_raster":
            try:
                lines = ocr.extract(rendered)
                text_available = bool(lines)
                if not lines:
                    limitations.append("No readable text found. Automatic detection cannot establish safe redaction boundaries.")
            except (RuntimeError, OSError):
                lines = []
                text_available = False
                limitations.append("Local OCR could not complete. Check Tesseract installation or use a clearer single-page sample.")
        if risky:
            limitations.append("Unsupported PDF structures: " + ", ".join(sorted(set(risky))) + ". Export is blocked.")
        if signed:
            limitations.append("Digital-signature indicators detected. Modification is blocked; signature validity was not checked.")
        extracted = {"lines": lines, "pages": len(doc), "signed": signed, "limitations": limitations,
                     "can_redact": bool(text_available and not risky and not signed),
                     "coverage": "text_layer_only" if processing_path == "pdf_text" else "ocr_supported_regions",
                     "processing_path": processing_path, "type": "PDF", "qr": "detected" if ocr.qr_present(rendered) else "not_detected"}
    detail = "Used native text extraction without OCR." if processing_path == "pdf_text" else "Selected local OCR for rendered page pixels; no hidden text is retained in a protected raster output."
    return {"extracted": extracted, "trace": state["trace"] + [{"agent": "Document Intelligence", "tool": "Extract PDF text" if processing_path == "pdf_text" else "Local OCR", "detail": detail}]}


def inspect_image(state):
    try:
        with Image.open(BytesIO(state["data"])) as image:
            width, height = image.size
            if width * height > MAX_PIXELS:
                raise InputError("Choose an image of 20 megapixels or smaller.")
            if getattr(image, "n_frames", 1) != 1:
                raise InputError("This prototype supports single-page documents only.")
            image.load()
            cleaned = ocr.clean_image(image)
    except InputError:
        raise
    except Exception as exc:
        raise InputError("This image is corrupted or cannot be opened.") from exc
    limitations = []
    try:
        lines = ocr.extract(cleaned)
        if not lines:
            limitations.append("No readable text found. Automatic detection cannot establish safe redaction boundaries.")
    except (RuntimeError, OSError):
        lines = []
        limitations.append("Local OCR could not complete. Check Tesseract installation or use a clearer single-page sample.")
    return {"extracted": {"lines": lines, "pages": 1, "signed": False, "can_redact": bool(lines),
                          "limitations": limitations, "processing_path": "image",
                          "coverage": "ocr_supported_regions", "type": "Image", "qr": "detected" if ocr.qr_present(cleaned) else "not_detected"},
            "trace": state["trace"] + [{"agent": "Document Intelligence", "tool": "Local OCR", "detail": "Read text and independently located character boxes using local Tesseract. Low-confidence boundaries remain ineligible."}]}


def detect_pii(state):
    findings = []
    extracted = state["extracted"]
    for line in extracted["lines"]:
        occupied = []
        for kind, pattern in PATTERNS.items():
            for match in pattern.finditer(line["text"]):
                if any(match.start() < end and match.end() > start for start, end in occupied):
                    continue
                occupied.append(match.span())
                chars = line["chars"][match.start():match.end()]
                region = fitz.Rect(chars[0]["bbox"])
                for char in chars[1:]:
                    region |= fitz.Rect(char["bbox"])
                # Only the first eight digit boxes are removed for Aadhaar.
                selected = [char for char in chars if char["c"].isdigit()][:8] if kind == "aadhaar" else chars
                rects = [list(char["bbox"]) for char in selected if not char["c"].isspace()]
                value = match.group()
                locatable = all(char.get("precise", True) for char in chars)
                digits = [char for char in chars if char["c"].isdigit()]
                if kind == "aadhaar" and len(digits) == 12:
                    margin = 4 if extracted["processing_path"] != "pdf_text" else -0.1
                    locatable = locatable and digits[7]["bbox"][2] + margin < digits[8]["bbox"][0]
                    if extracted["processing_path"] != "pdf_text":
                        heights = [digit["bbox"][3] - digit["bbox"][1] for digit in digits]
                        # Reject fused OCR boxes that reach into a neighboring line.
                        locatable = locatable and min(heights) > 0 and max(heights) <= min(heights) * 1.35
                last_four_rect = None
                if kind == "aadhaar" and len(digits) == 12:
                    retained = fitz.Rect(digits[8]["bbox"])
                    for digit in digits[9:]:
                        retained |= fitz.Rect(digit["bbox"])
                    last_four_rect = list(retained)
                findings.append({"id": f"finding-{len(findings) + 1}", "category": kind, "label": LABELS[kind],
                                 "masked_value": mask(kind, value), "value": value, "page": line["page"],
                                 "region": [region.x0 / line["width"], region.y0 / line["height"], region.x1 / line["width"], region.y1 / line["height"]],
                                 "rects": rects, "last_four_rect": last_four_rect, "locatable": locatable,
                                 "text_style": {"size": chars[0]["font_size"], "color": chars[0]["font_color"], "baseline": chars[0]["origin"][1]} if extracted["processing_path"] == "pdf_text" else None,
                                 "confidence": "Pattern match; identity not verified", "checksum_valid": verhoeff_valid(value) if kind == "aadhaar" else None,
                                 "priority": "high" if kind in ("aadhaar", "pan") else "medium"})
    text = " ".join(line["text"] for line in extracted["lines"]).lower()
    categories = {f["category"] for f in findings}
    classification = "Aadhaar-like document" if "aadhaar" in categories and "aadhaar" in text else "PAN-like document" if "pan" in categories and "pan" in text else "Generic document"
    report = {"filename": state["filename"], "size": len(state["data"]), "file_type": extracted["type"],
              "pages": extracted["pages"], "classification": classification, "findings": findings,
              "limitations": extracted["limitations"], "can_redact": extracted["can_redact"],
              "authentication": {"signature_indicator": extracted["signed"], "qr_status": extracted["qr"], "signature_validity": "not_verified"},
              "coverage": extracted["coverage"], "processing_path": extracted["processing_path"], "mode": "Rule-based · local LangGraph workflow"}
    report["_address_disclosure"] = comparison.inspect_lines(extracted)
    return {"report": report, "trace": state["trace"] + [{"agent": "Document Intelligence", "tool": "Detect structured PII", "detail": f"Located {len(findings)} pattern matches. Raw values omitted from the activity log."}]}


def privacy_decisions(state):
    report = state["report"]
    requirements = state["requirements"]
    required = {item.strip().lower() for item in requirements.get("required_fields", [])}
    for finding in report["findings"]:
        kind = finding["category"]
        needed = kind in required
        finding["recommended"] = not needed
        if needed:
            reason = "The portal states this field is required. Keep it unless the recipient confirms masking is accepted."
        elif kind == "aadhaar":
            reason = "Consider hiding the first eight digits. Prefer an officially issued masked Aadhaar; acceptance of custom masking is unknown."
        elif kind == "pan":
            reason = "Mask only if the recipient does not require your PAN. Acceptance has not been confirmed."
            finding["recommended"] = False
        else:
            reason = "This field is not explicitly listed as required. Review whether the recipient needs it before sharing."
        finding["reason"] = reason
    max_bytes = requirements.get("max_bytes", 2 * 1024 * 1024)
    accepted = requirements.get("formats", ["pdf"])
    actual_format = "pdf" if report["file_type"] == "PDF" else "png" if state["data"].startswith(b"\x89PNG") else "jpeg"
    report["compatibility"] = {"size_ok": len(state["data"]) <= max_bytes, "format_ok": actual_format in accepted,
                               "max_bytes": max_bytes, "accepted_formats": accepted, "recipient_acceptance": "unknown"}
    report["requirements"] = requirements
    report["warnings"] = ["QR code detected: it may retain identifying information. Prefer an official masked document." if report["authentication"]["qr_status"] == "detected" else "No QR indicator detected by the supported check; absence is not guaranteed.",
                          "Custom redaction may affect verification. Recipient acceptance is unknown."]
    return {"report": report, "trace": state["trace"] + [{"agent": "Privacy Decision", "tool": "Compare upload requirements", "detail": "Compared declared required fields, size, and format. Recipient acceptance remains unknown."},
                                                         {"agent": "Privacy Decision", "tool": "Recommend actions", "detail": "Prepared reviewable suggestions. No changes applied without approval."}]}


document_builder = StateGraph(GraphState)
document_builder.add_node("inspect", inspect_file)
document_builder.add_node("pdf", extract_pdf)
document_builder.add_node("image", inspect_image)
document_builder.add_node("detect", detect_pii)
document_builder.add_edge(START, "inspect")
document_builder.add_conditional_edges("inspect", lambda s: s["kind"], {"pdf": "pdf", "image": "image"})
document_builder.add_edge("pdf", "detect")
document_builder.add_edge("image", "detect")
document_builder.add_edge("detect", END)
document_graph = document_builder.compile()

privacy_builder = StateGraph(GraphState)
privacy_builder.add_node("evaluate", privacy_decisions)
privacy_builder.add_edge(START, "evaluate")
privacy_builder.add_edge("evaluate", END)
privacy_graph = privacy_builder.compile()

workflow_builder = StateGraph(GraphState)
workflow_builder.add_node("document_intelligence", document_graph)
workflow_builder.add_node("privacy_decision", privacy_graph)
workflow_builder.add_edge(START, "document_intelligence")
workflow_builder.add_edge("document_intelligence", "privacy_decision")
workflow_builder.add_edge("privacy_decision", END)
workflow = workflow_builder.compile()


def analyze(data, filename, requirements):
    start = perf_counter()
    # Override inherited tracing settings so document state cannot be exported.
    with tracing_context(enabled=False):
        result = workflow.invoke({"data": data, "filename": filename, "requirements": requirements}, {"recursion_limit": 12, "callbacks": []})
    report = result["report"]
    report["trace"] = result["trace"]
    report["elapsed_ms"] = round((perf_counter() - start) * 1000)
    return report


def public_report(report):
    return {**{key: value for key, value in report.items() if not key.startswith("_")}, "findings": [{k: v for k, v in finding.items() if k not in ("value", "rects", "last_four_rect", "text_style")} for finding in report["findings"]]}


def redact(data, report, approved_ids):
    if not report["can_redact"]:
        raise InputError("This document cannot be reliably redacted by the prototype. Review its limitations.")
    approved = [finding for finding in report["findings"] if finding["id"] in approved_ids]
    if not approved or set(approved_ids) - {finding["id"] for finding in approved}:
        raise InputError("Select valid findings and approve their redaction first.")
    if any(not finding["locatable"] for finding in approved):
        raise InputError("Reliable character boundaries could not be established for a selected finding. Use a clearer sample; no output was generated.")
    path = report["processing_path"]
    modified_image = None
    source_image = raster_image(data)
    retained_positions = True
    try:
        plans = {finding["id"]: masking.plan(finding, source_image, pdf=path == "pdf_text") for finding in approved}
    except masking.MaskingError as exc:
        raise InputError(str(exc)) from exc
    replacements = {}
    if path == "pdf_text":
        with fitz.open(stream=data, filetype="pdf") as doc:
            for finding in approved:
                page = doc[0]
                if not page.search_for(finding["value"]):
                    raise InputError("A selected value could not be reliably located. No output was generated.")
                for part in plans[finding["id"]]:
                    page.add_redact_annot(fitz.Rect(part["rect"]), fill=tuple(channel / 255 for channel in part["background"]))
            doc[0].apply_redactions(images=2, graphics=0)
            for parts in plans.values():
                for part in parts:
                    doc[0].insert_text(fitz.Point(*part["origin"]), part["text"], fontsize=part["size"], fontname="helv", color=tuple(channel / 255 for channel in part["foreground"]))
            doc.set_metadata({})
            if doc.get_xml_metadata():
                doc.del_xml_metadata()
            output = doc.tobytes(garbage=4, deflate=True)
        with fitz.open(stream=output, filetype="pdf") as check:
            text = normalize(check[0].get_text(sort=True))
            retained_positions = all(re.sub(r"\D", "", finding["value"])[-4:] in normalize(check[0].get_textbox(fitz.Rect(finding["last_four_rect"]))) for finding in approved if finding["category"] == "aadhaar")
            replacements = {finding["id"]: masking.pdf_replacement_matches(check[0], plans[finding["id"]]) for finding in approved}
        mime = "application/pdf"
    else:
        try:
            modified_image = masking.render(source_image, plans)
        except masking.MaskingError as exc:
            raise InputError(str(exc)) from exc
        expected_image = modified_image.copy()
        if path == "pdf_raster":
            png = BytesIO()
            modified_image.save(png, format="PNG")
            with fitz.open() as doc:
                page = doc.new_page(width=modified_image.width / 2, height=modified_image.height / 2)
                page.insert_image(page.rect, stream=png.getvalue())
                output = doc.tobytes(garbage=4, deflate=True)
            mime = "application/pdf"
        else:
            buffer = BytesIO()
            modified_image.save(buffer, format="PNG")
            output = buffer.getvalue()
            mime = "image/png"
        # Reopen exported pixels, not the in-memory source used for masking.
        reopened = raster_image(output)
        try:
            text = normalize(ocr.read_text(reopened))
        except (RuntimeError, OSError):
            return output, {"status": "incomplete", "checks": [], "preserved_last_four": False,
                            "technical_compatibility": False, "output_size": len(output), "approved_count": len(approved),
                            "mime": mime, "limitations": "Output OCR could not complete. Download is blocked."}
        modified_image = reopened
        replacements = {finding["id"]: masking.raster_replacement_matches(reopened, expected_image, plans[finding["id"]]) for finding in approved}
        retained_positions = all(ImageChops.difference(source_image.crop(tuple(int(value) for value in finding["last_four_rect"])), reopened.crop(tuple(int(value) for value in finding["last_four_rect"]))).getbbox() is None for finding in approved if finding["category"] == "aadhaar")
    checks = []
    for finding in approved:
        target = normalize(finding["value"])
        if finding["category"] == "aadhaar":
            target = re.sub(r"\D", "", finding["value"])[:8]
        checks.append({"finding_id": finding["id"], "removed": target not in text, "replacement_rendered": replacements[finding["id"]]})
    preserved = retained_positions and all(re.sub(r"\D", "", finding["value"])[-4:] in text for finding in approved if finding["category"] == "aadhaar")
    passed = all(item["removed"] and item["replacement_rendered"] for item in checks) and preserved
    compatibility = report["compatibility"]
    output_format = "pdf" if mime == "application/pdf" else "png"
    technically_compatible = len(output) <= compatibility["max_bytes"] and output_format in compatibility["accepted_formats"]
    verification = {"status": "passed_supported_checks" if passed and technically_compatible else "failed", "checks": checks,
                    "preserved_last_four": preserved, "technical_compatibility": technically_compatible,
                    "output_size": len(output), "approved_count": len(approved), "mime": mime,
                    "limitations": "Supported target-removal, readable-mask rendering, and technical checks only. QR payloads, cryptographic validity, authenticity, and recipient acceptance are not verified."}
    return output, verification


def raster_image(data):
    if data.startswith(b"%PDF-"):
        with fitz.open(stream=data, filetype="pdf") as doc:
            return Image.open(BytesIO(doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes("png"))).convert("RGB")
    with Image.open(BytesIO(data)) as image:
        return ocr.clean_image(image)


def preview(data, page_number=0):
    if data.startswith(b"%PDF-"):
        with fitz.open(stream=data, filetype="pdf") as doc:
            if page_number < 0 or page_number >= len(doc):
                raise InputError("Page does not exist.")
            page = doc[page_number]
            if page.rect.width * page.rect.height * 2.25 > MAX_PIXELS:
                raise InputError("Page is too large to preview.")
            return page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).tobytes("png")
    with Image.open(BytesIO(data)) as image:
        if page_number != 0:
            raise InputError("Page does not exist.")
        image = ocr.clean_image(image)
        image.thumbnail((1400, 1400))
        output = BytesIO()
        image.convert("RGB").save(output, format="PNG")
        return output.getvalue()


def sample_document(kind="aadhaar"):
    doc = fitz.open()
    page = doc.new_page(width=620, height=420)
    page.draw_rect(fitz.Rect(0, 0, 620, 420), color=None, fill=(0.98, 0.98, 1))
    page.draw_rect(fitz.Rect(30, 30, 590, 390), color=(0.86, 0.86, 0.92), fill=(1, 1, 1), width=1)
    page.draw_rect(fitz.Rect(30, 30, 590, 36), color=None, fill=(0.43, 0.35, 0.88))
    page.insert_text((54, 68), "PRIVACYGATE / SYNTHETIC SAMPLE", fontsize=10, color=(0.43, 0.35, 0.75))
    title = "PAN-like sample" if kind == "pan" else "Aadhaar-like sample"
    page.insert_text((54, 112), title, fontsize=26, color=(0.12, 0.13, 0.21))
    page.insert_text((54, 142), "DEMO ONLY - NOT A VALID IDENTITY DOCUMENT", fontsize=10, color=(0.65, 0.28, 0.15))
    page.draw_rect(fitz.Rect(54, 166, 145, 274), color=None, fill=(0.93, 0.92, 0.98))
    page.draw_circle(fitz.Point(100, 201), 17, color=None, fill=(0.69, 0.65, 0.85))
    page.draw_rect(fitz.Rect(74, 225, 126, 258), color=None, fill=(0.69, 0.65, 0.85))
    page.insert_text((170, 185), "NAME", fontsize=9, color=(0.5, 0.51, 0.58))
    page.insert_text((170, 208), "Alex Sample", fontsize=18, color=(0.15, 0.16, 0.24))
    page.insert_text((170, 232), "DOB: 01 Jan 2000   /   Fictional identity", fontsize=11, color=(0.35, 0.36, 0.43))
    prefix = "23456789012"
    synthetic = next(prefix + str(digit) for digit in range(10) if verhoeff_valid(prefix + str(digit)))
    number = " ".join(synthetic[index:index + 4] for index in range(0, 12, 4))
    page.insert_text((170, 267), "ABCDE1234F" if kind == "pan" else number, fontsize=24, color=(0.15, 0.16, 0.24))
    page.draw_line(fitz.Point(54, 294), fitz.Point(566, 294), color=(0.9, 0.9, 0.94))
    page.insert_text((54, 321), "Email: alex.sample@example.com", fontsize=12, color=(0.32, 0.33, 0.41))
    page.insert_text((54, 345), "Phone: 9876543210", fontsize=12, color=(0.32, 0.33, 0.41))
    page.insert_text((54, 374), "All identifiers are illustrative. For local prototype testing only.", fontsize=9, color=(0.5, 0.51, 0.58))
    result = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return result
