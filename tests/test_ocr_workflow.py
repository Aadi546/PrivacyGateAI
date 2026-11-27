import copy
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import fitz
from PIL import Image
from fastapi.testclient import TestClient

from backend import engine, ocr, masking
from backend.fixtures import FIXTURES, make_fixture
from backend.main import app, SESSIONS, TOKEN

RULES = {"formats": ["pdf", "png", "jpeg"], "max_bytes": 2 * 1024 * 1024, "required_fields": []}


class OCRWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scan = make_fixture("aadhaar-scan.png")
        cls.report = engine.analyze(cls.scan, "synthetic.png", RULES)

    def test_scanned_aadhaar_approved_pixel_redaction(self):
        finding = next(f for f in self.report["findings"] if f["category"] == "aadhaar")
        self.assertTrue(finding["locatable"])
        self.assertTrue(finding["checksum_valid"])
        output, verification = engine.redact(self.scan, self.report, [finding["id"]])
        self.assertEqual(verification["status"], "passed_supported_checks")
        self.assertTrue(verification["preserved_last_four"])
        with Image.open(io.BytesIO(output)) as image:
            self.assertFalse(image.getexif())
            self.assertNotIn("exif", image.info)
        self.assertNotEqual(output, self.scan)

    def test_all_approved_categories_in_image(self):
        output, verification = engine.redact(self.scan, self.report, [f["id"] for f in self.report["findings"]])
        self.assertEqual(verification["status"], "passed_supported_checks")
        self.assertEqual(verification["approved_count"], 3)
        self.assertTrue(all(check['replacement_rendered'] for check in verification['checks']))

    def test_masks_are_glyphs_not_solid_bars_and_do_not_change_other_pixels(self):
        import numpy as np
        source = engine.raster_image(self.scan)
        plans = {finding['id']: masking.plan(finding, source) for finding in self.report['findings']}
        output, result = engine.redact(self.scan, self.report, list(plans))
        self.assertEqual(result['status'], 'passed_supported_checks')
        result_image = engine.raster_image(output)
        actual = np.asarray(result_image)
        original = np.asarray(source)
        allowed = np.zeros(actual.shape[:2], dtype=bool)
        for parts in plans.values():
            for part in parts:
                x0, y0, x1, y1 = masking.clipped_rect(part['rect'], source)
                allowed[y0:y1 + 1, x0:x1 + 1] = True
                region = actual[y0:y1, x0:x1].astype(int)
                dark = np.max(np.abs(region - np.array(part['background'])), axis=2) > 40
                self.assertGreater(float(dark.mean()), .03)
                self.assertLess(float(dark.mean()), .65, 'A readable mask must not become a solid bar')
        self.assertTrue(np.array_equal(actual[~allowed], original[~allowed]))

    def test_jpeg_input_gets_verified_readable_png(self):
        buffer = io.BytesIO()
        with Image.open(io.BytesIO(self.scan)) as image:
            image.save(buffer, format='JPEG', quality=95)
        data = buffer.getvalue()
        report = engine.analyze(data, 'scan.jpg', RULES)
        finding = next(f for f in report['findings'] if f['category'] == 'aadhaar')
        output, result = engine.redact(data, report, [finding['id']])
        self.assertEqual(result['status'], 'passed_supported_checks')
        self.assertTrue(result['checks'][0]['replacement_rendered'])
        self.assertTrue(output.startswith(b'\x89PNG'))

    def test_nonuniform_background_rejected_and_tampered_mask_detected(self):
        import numpy as np
        source = engine.raster_image(self.scan)
        finding = next(f for f in self.report['findings'] if f['category'] == 'aadhaar')
        parts = masking.plan(finding, source)
        expected = masking.render(source, {finding['id']: parts})
        from PIL import ImageDraw
        ImageDraw.Draw(expected).rectangle(masking.clipped_rect(parts[0]['rect'], expected), fill='black')
        pristine = masking.render(source, {finding['id']: parts})
        self.assertFalse(masking.raster_replacement_matches(expected, pristine, parts))
        x0, y0, x1, y1 = masking.clipped_rect(parts[0]['rect'], source)
        noisy = source.copy()
        patch_pixels = np.random.default_rng(10).integers(0, 256, (y1-y0+12, x1-x0+12, 3), dtype=np.uint8)
        noisy.paste(Image.fromarray(patch_pixels), (x0-6, y0-6))
        with self.assertRaises(masking.MaskingError):
            masking.plan(finding, noisy)

    def test_missing_replacement_blocks_verification(self):
        finding = next(f for f in self.report['findings'] if f['category'] == 'aadhaar')
        with patch.object(masking, 'raster_replacement_matches', return_value=False):
            _, result = engine.redact(self.scan, self.report, [finding['id']])
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['checks'][0]['replacement_rendered'])

    def test_pan_image_and_required_retention_recommendation(self):
        report = engine.analyze(make_fixture("pan-scan.png"), "pan.png", {**RULES, "required_fields": ["pan", "phone", "email"]})
        self.assertEqual(report["classification"], "PAN-like document")
        pan = next(f for f in report["findings"] if f["category"] == "pan")
        self.assertFalse(pan["recommended"])
        self.assertIn("required", pan["reason"])
        output, verification = engine.redact(make_fixture("pan-scan.png"), report, [pan["id"]])
        self.assertEqual(verification["status"], "passed_supported_checks")

    def test_qr_detected_and_warned_without_decoding_payload(self):
        report = engine.analyze(make_fixture("qr-sample.png"), "qr.png", RULES)
        self.assertEqual(report["authentication"]["qr_status"], "detected")
        self.assertIn("official", report["warnings"][0])
        self.assertNotIn("PRIVACYGATE-SYNTHETIC-DEMO-ONLY", str(engine.public_report(report)))

    def test_oversized_fixture_incompatibility(self):
        data = make_fixture("oversized.png")
        self.assertGreater(len(data), 2 * 1024 * 1024)
        report = engine.analyze(data, "oversized.png", RULES)
        self.assertFalse(report["compatibility"]["size_ok"])

    def test_unreliable_boundaries_stop_without_guessing(self):
        with patch.object(ocr, "MIN_CONFIDENCE", 101):
            report = engine.analyze(self.scan, "low-confidence.png", RULES)
        aadhaar = next(f for f in report["findings"] if f["category"] == "aadhaar")
        self.assertFalse(aadhaar["locatable"])
        with self.assertRaises(engine.InputError):
            engine.redact(self.scan, report, [aadhaar["id"]])

    def test_failed_ocr_verification_does_not_pass(self):
        finding = next(f for f in self.report["findings"] if f["category"] == "aadhaar")
        with patch.object(ocr, "read_text", return_value=finding["value"]):
            _, result = engine.redact(self.scan, self.report, [finding["id"]])
        self.assertEqual(result["status"], "failed")
        with patch.object(ocr, "read_text", side_effect=RuntimeError("OCR timeout")):
            _, result = engine.redact(self.scan, self.report, [finding["id"]])
        self.assertEqual(result["status"], "incomplete")

    def test_size_and_format_are_part_of_verification_gate(self):
        data = make_fixture("aadhaar-text.pdf")
        for rules in ({**RULES, "max_bytes": 10}, {**RULES, "formats": ["jpeg"]}):
            report = engine.analyze(data, "document.pdf", rules)
            _, result = engine.redact(data, report, [report["findings"][0]["id"]])
            self.assertEqual(result["status"], "failed")
            self.assertFalse(result["technical_compatibility"])

    def test_raster_pdf_rebuilt_without_old_text_layer(self):
        with fitz.open() as doc:
            page = doc.new_page(width=620, height=420)
            page.insert_image(page.rect, stream=self.scan)
            data = doc.tobytes()
        report = engine.analyze(data, "scan.pdf", RULES)
        self.assertEqual(report["processing_path"], "pdf_raster")
        finding = next(f for f in report["findings"] if f["category"] == "aadhaar")
        output, result = engine.redact(data, report, [finding["id"]])
        self.assertEqual(result["status"], "passed_supported_checks")
        with fitz.open(stream=output, filetype="pdf") as doc:
            self.assertEqual(doc[0].get_text().strip(), "")

    def test_each_signature_indicator_blocks_modification(self):
        for key, value in (("ByteRange", "[0 1 2 3]"), ("AcroForm", "<< /SigFlags 1 >>")):
            with fitz.open(stream=make_fixture("aadhaar-text.pdf"), filetype="pdf") as doc:
                doc.xref_set_key(doc.pdf_catalog(), key, value)
                data = doc.tobytes()
            report = engine.analyze(data, "indicator.pdf", RULES)
            self.assertTrue(report["authentication"]["signature_indicator"], key)
            self.assertFalse(report["can_redact"])

    def test_image_download_api_has_correct_type_and_extension(self):
        SESSIONS.clear()
        headers = {"X-PrivacyGate-Token": TOKEN}
        with TestClient(app, base_url="http://127.0.0.1:8765") as client:
            report = client.post("/api/analyze", headers=headers, files={"file": ("demo.jpg", self.scan)}, data={"requirements": __import__('json').dumps(RULES)}).json()
            sid = report["session_id"]
            finding = next(f for f in report["findings"] if f["category"] == "aadhaar")
            result = client.post(f"/api/sessions/{sid}/redact", headers=headers, json={"finding_ids": [finding["id"]], "approved": True})
            self.assertEqual(result.json()["verification"]["status"], "passed_supported_checks")
            output = client.get(f"/api/sessions/{sid}/download", headers=headers)
            self.assertEqual(output.headers["content-type"], "image/png")
            self.assertIn("protected-demo.png", output.headers["content-disposition"])


class DiscoveryTests(unittest.TestCase):
    def test_inherited_cloud_tracing_is_disabled_during_analysis(self):
        from langsmith.utils import tracing_is_enabled
        def inspect_context(*args, **kwargs):
            self.assertFalse(tracing_is_enabled())
            return {"report": {}, "trace": []}
        with patch.dict(os.environ, {"LANGSMITH_TRACING": "true", "LANGCHAIN_TRACING_V2": "true"}), patch.object(engine.workflow, "invoke", side_effect=inspect_context):
            engine.analyze(b"synthetic", "sample", RULES)

    def test_explicit_invalid_override_errors_instead_of_guessing(self):
        with patch.dict(os.environ, {"TESSERACT_CMD": "/missing/explicit-tesseract"}), patch("backend.ocr.shutil.which", return_value=None), patch.object(Path, "is_file", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "TESSERACT_CMD"):
                ocr.find_tesseract()

    def test_both_homebrew_paths_are_checked(self):
        for path in ("/usr/local/bin/tesseract", "/opt/homebrew/bin/tesseract"):
            with patch.dict(os.environ, {}, clear=True), patch("backend.ocr.shutil.which", return_value=None), patch.object(Path, "is_file", lambda candidate: candidate.as_posix() == path):
                self.assertEqual(ocr.find_tesseract(), path)

    def test_no_installation_has_clear_error(self):
        with patch.dict(os.environ, {}, clear=True), patch("backend.ocr.shutil.which", return_value=None), patch.object(Path, "is_file", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "both Homebrew"):
                ocr.find_tesseract()
