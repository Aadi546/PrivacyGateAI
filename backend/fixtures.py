"""Six clearly marked synthetic fixtures. No real identity documents."""

import json
from io import BytesIO
from pathlib import Path

import cv2
import fitz
import numpy as np
from PIL import Image

from .engine import sample_document

FIXTURES = {
    "aadhaar-text.pdf": "Text PDF with a Verhoeff-valid illustrative identifier",
    "aadhaar-scan.png": "Scanned Aadhaar-like image; main demo",
    "pan-scan.png": "Scanned PAN-like image",
    "signature-indicator.pdf": "Unsigned test signature field; must block modification",
    "qr-sample.png": "Synthetic image with a detectable QR code",
    "oversized.png": "Readable synthetic card plus deterministic noise; exceeds 2 MB",
}


def image_from_pdf(data):
    with fitz.open(stream=data, filetype="pdf") as doc:
        return Image.open(BytesIO(doc[0].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False).tobytes("png"))).convert("RGB")


def make_fixture(name):
    if name not in FIXTURES:
        raise ValueError("Unknown synthetic fixture")
    data = sample_document("pan" if name == "pan-scan.png" else "aadhaar")
    if name == "aadhaar-text.pdf":
        return data
    if name == "signature-indicator.pdf":
        with fitz.open(stream=data, filetype="pdf") as doc:
            widget = fitz.Widget()
            widget.field_name = "SyntheticSignatureIndicator"
            widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
            widget.rect = fitz.Rect(470, 170, 565, 240)
            doc[0].add_widget(widget)
            return doc.tobytes(garbage=4)
    image = image_from_pdf(data)
    if name == "qr-sample.png":
        code = cv2.QRCodeEncoder_create().encode("PRIVACYGATE-SYNTHETIC-DEMO-ONLY")
        code = cv2.copyMakeBorder(code, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
        qr = Image.fromarray(code).resize((270, 270), Image.Resampling.NEAREST)
        image.paste(qr, (1400, 495))
    elif name == "oversized.png":
        noise = Image.fromarray(np.random.default_rng(42).integers(0, 256, (550, image.width, 3), dtype=np.uint8))
        enlarged = Image.new("RGB", (image.width, image.height + noise.height), "white")
        enlarged.paste(image, (0, 0))
        enlarged.paste(noise, (0, image.height))
        image = enlarged
    result = BytesIO()
    image.save(result, format="PNG")
    return result.getvalue()


def generate(destination=None):
    destination = Path(destination or Path(__file__).resolve().parent.parent / "sample-documents")
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, description in FIXTURES.items():
        data = make_fixture(name)
        (destination / name).write_bytes(data)
        manifest.append({"filename": name, "description": description, "bytes": len(data), "synthetic": True})
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    for item in generate():
        print(f"{item['filename']}: {item['bytes']} bytes (synthetic)")
