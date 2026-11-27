import hashlib
import io
import json
import time
import unittest

import fitz
from PIL import Image
from fastapi.testclient import TestClient

from backend import engine
from backend.main import app, SESSIONS, TOKEN, TTL

RULES = {"formats": ["pdf", "png", "jpeg"], "max_bytes": 2 * 1024 * 1024, "required_fields": []}


def pdf_with_text(text):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 100), text)
        return doc.tobytes()


class DocumentTests(unittest.TestCase):
    def test_readable_mask_formats(self):
        self.assertEqual(engine.mask('aadhaar', '2345 6789 0124'), 'xxxx xxxx 0124')
        self.assertEqual(engine.mask('phone', '9876543210'), 'xxxxxx3210')
        self.assertEqual(engine.mask('phone', '+91 9876543210'), 'xxxxxxxx3210')
        self.assertEqual(engine.mask('pan', 'ABCDE1234F'), 'ABxxxxxx4F')
        self.assertEqual(engine.mask('email', 'alex.sample@example.com'), 'a***@example.com')

    def test_native_pdf_contains_readable_masks_and_no_original_targets(self):
        for kind in ('aadhaar', 'pan'):
            data = engine.sample_document(kind)
            report = engine.analyze(data, 'sample.pdf', RULES)
            output, result = engine.redact(data, report, [f['id'] for f in report['findings']])
            self.assertEqual(result['status'], 'passed_supported_checks')
            self.assertTrue(all(check['replacement_rendered'] for check in result['checks']))
            with fitz.open(stream=output, filetype='pdf') as doc:
                text = engine.normalize(doc[0].get_text(sort=True))
                for finding in report['findings']:
                    self.assertNotIn(engine.normalize(finding['value']), text)
                    self.assertIn(engine.normalize(finding['masked_value']), text)

    def setUp(self):
        self.data = engine.sample_document()

    def test_detects_and_routes_without_ocr(self):
        report = engine.analyze(self.data, "sample.pdf", RULES)
        self.assertEqual({f["category"] for f in report["findings"]}, {"aadhaar", "phone", "email"})
        self.assertTrue(report["can_redact"])
        self.assertEqual(report["classification"], "Aadhaar-like document")
        self.assertIn("Extract PDF text", [entry["tool"] for entry in report["trace"]])
        public = engine.public_report(report)
        self.assertNotIn("value", public["findings"][0])
        for finding in report["findings"]:
            self.assertNotIn(finding["value"], json.dumps(public))

    def test_redaction_removes_recoverable_text_and_preserves_last_four(self):
        original_hash = hashlib.sha256(self.data).hexdigest()
        report = engine.analyze(self.data, "sample.pdf", RULES)
        output, verification = engine.redact(self.data, report, [finding["id"] for finding in report["findings"]])
        self.assertEqual(verification["status"], "passed_supported_checks")
        self.assertEqual(hashlib.sha256(self.data).hexdigest(), original_hash)
        with fitz.open(stream=output, filetype="pdf") as doc:
            text = " ".join(page.get_text() for page in doc)
            self.assertNotIn("23456789", engine.normalize(text))
            self.assertNotIn("alex.sample@example.com", text)
            self.assertNotIn("9876543210", text)
            self.assertIn("0124", text)
            self.assertIn("Alex Sample", text)
            self.assertFalse(doc.is_dirty)

    def test_selective_redaction_preserves_unselected_fields(self):
        report = engine.analyze(self.data, "sample.pdf", RULES)
        target = next(f for f in report["findings"] if f["category"] == "email")
        output, verification = engine.redact(self.data, report, [target["id"]])
        with fitz.open(stream=output, filetype="pdf") as doc:
            text = " ".join(page.get_text() for page in doc)
            self.assertIn("2345 6789 0124", text)
            self.assertIn("9876543210", text)
            self.assertNotIn(target["value"], text)
        self.assertEqual(verification["status"], "passed_supported_checks")

    def test_required_field_is_not_recommended_for_redaction(self):
        report = engine.analyze(self.data, "sample.pdf", {**RULES, "required_fields": ["aadhaar"]})
        finding = next(f for f in report["findings"] if f["category"] == "aadhaar")
        self.assertFalse(finding["recommended"])
        self.assertIn("required", finding["reason"])

    def test_pan_is_not_selected_by_default(self):
        report = engine.analyze(engine.sample_document("pan"), "pan.pdf", RULES)
        self.assertEqual(report["classification"], "PAN-like document")
        self.assertFalse(next(f for f in report["findings"] if f["category"] == "pan")["recommended"])

    def test_image_and_scan_fail_closed(self):
        buffer = io.BytesIO()
        Image.new("RGB", (100, 100), "white").save(buffer, "PNG")
        image = buffer.getvalue()
        report = engine.analyze(image, "scan.png", RULES)
        self.assertFalse(report["can_redact"])
        self.assertEqual(report["coverage"], "ocr_supported_regions")
        self.assertTrue(engine.preview(image).startswith(b"\x89PNG"))
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_image(fitz.Rect(20, 20, 120, 120), stream=image)
            scanned = doc.tobytes()
        report = engine.analyze(scanned, "scan.pdf", RULES)
        self.assertFalse(report["can_redact"])
        self.assertTrue(report["limitations"])

    def test_no_pii_does_not_claim_safe(self):
        report = engine.analyze(pdf_with_text("A fictional certificate with no supported identifiers."), "certificate.pdf", RULES)
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["authentication"]["qr_status"], "not_detected")
        self.assertEqual(report["compatibility"]["recipient_acceptance"], "unknown")

    def test_signed_indicator_blocks_redaction(self):
        with fitz.open(stream=self.data, filetype="pdf") as doc:
            widget = fitz.Widget()
            widget.field_name = "SyntheticSignature"
            widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
            widget.rect = fitz.Rect(400, 150, 550, 190)
            doc[0].add_widget(widget)
            signed = doc.tobytes()
        report = engine.analyze(signed, "indicator.pdf", RULES)
        self.assertTrue(report["authentication"]["signature_indicator"])
        self.assertFalse(report["can_redact"])
        with self.assertRaises(engine.InputError):
            engine.redact(signed, report, [report["findings"][0]["id"]])

    def test_invalid_encrypted_and_too_many_pages(self):
        for data in (b"random content", b"%PDF-broken", b""):
            with self.assertRaises(engine.InputError):
                engine.analyze(data, "invalid.pdf", RULES)
        with fitz.open(stream=self.data, filetype="pdf") as doc:
            encrypted = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner-test", user_pw="user-test")
        with self.assertRaises(engine.InputError):
            engine.analyze(encrypted, "encrypted.pdf", RULES)
        with fitz.open() as doc:
            for _ in range(6):
                doc.new_page()
            data = doc.tobytes()
        with self.assertRaises(engine.InputError):
            engine.analyze(data, "long.pdf", RULES)

    def test_compatibility_and_unknown_approvals(self):
        report = engine.analyze(self.data, "sample.pdf", {**RULES, "max_bytes": 10, "formats": ["png"]})
        self.assertFalse(report["compatibility"]["size_ok"])
        self.assertFalse(report["compatibility"]["format_ok"])
        for ids in ([], ["unknown"]):
            with self.assertRaises(engine.InputError):
                engine.redact(self.data, report, ids)


class APITests(unittest.TestCase):
    def setUp(self):
        SESSIONS.clear()
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")
        self.headers = {"X-PrivacyGate-Token": TOKEN}

    def tearDown(self):
        self.client.close()
        SESSIONS.clear()

    def upload(self, data=None):
        return self.client.post("/api/analyze", headers=self.headers,
                                files={"file": ("sample.pdf", data or engine.sample_document(), "application/pdf")},
                                data={"requirements": json.dumps(RULES)})

    def test_auth_origin_and_host_protection(self):
        self.assertEqual(self.client.get("/api/sample/aadhaar-text.pdf").status_code, 401)
        self.assertEqual(self.client.get("/health").status_code, 401)
        self.assertEqual(self.client.get("/health", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get("/health", headers={"Origin": "https://evil.example", **self.headers}).status_code, 403)
        self.assertEqual(self.client.get("/health", headers={"Host": "evil.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/bootstrap", headers=self.headers).status_code, 404)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])

    def test_end_to_end_approval_and_download_gates(self):
        response = self.upload()
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        sid = report["session_id"]
        path = f"/api/sessions/{sid}"
        self.assertEqual(self.client.get(path + "/download", headers=self.headers).status_code, 409)
        self.assertEqual(self.client.get(path + "/preview/0", headers=self.headers).headers["content-type"], "image/png")
        ids = [finding["id"] for finding in report["findings"]]
        blocked = self.client.post(path + "/redact", headers=self.headers, json={"finding_ids": ids, "approved": False})
        self.assertEqual(blocked.status_code, 400)
        redacted = self.client.post(path + "/redact", headers=self.headers, json={"finding_ids": ids, "approved": True})
        self.assertEqual(redacted.status_code, 200, redacted.text)
        self.assertEqual(redacted.json()["verification"]["status"], "passed_supported_checks")
        output = self.client.get(path + "/download", headers=self.headers)
        self.assertEqual(output.status_code, 200)
        self.assertTrue(output.content.startswith(b"%PDF-"))
        self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get(path, headers=self.headers).status_code, 404)

    def test_invalid_requirements_and_session_expiry(self):
        response = self.client.post("/api/analyze", headers=self.headers, files={"file": ("a.pdf", engine.sample_document())}, data={"requirements": "[]"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.upload(b"not a PDF").status_code, 422)
        report = self.upload().json()
        SESSIONS[report["session_id"]].touched = time.monotonic() - TTL - 1
        self.assertEqual(self.client.get(f'/api/sessions/{report["session_id"]}', headers=self.headers).status_code, 404)

    def test_failed_technical_verification_blocks_download_server_side(self):
        response = self.client.post('/api/analyze', headers=self.headers, files={'file': ('sample.pdf', engine.sample_document())}, data={'requirements': json.dumps({**RULES, 'max_bytes': 100})})
        report = response.json()
        path = f'/api/sessions/{report["session_id"]}'
        result = self.client.post(path + '/redact', headers=self.headers, json={'finding_ids': [report['findings'][0]['id']], 'approved': True})
        self.assertEqual(result.json()['verification']['status'], 'failed')
        self.assertEqual(self.client.get(path + '/download', headers=self.headers).status_code, 409)

    def test_unknown_extension_origin_rejected_even_with_token(self):
        response = self.client.get('/health', headers={**self.headers, 'Origin': 'chrome-extension://' + 'a' * 32})
        self.assertEqual(response.status_code, 403)

    def test_download_requires_replacement_rendering_check(self):
        from unittest.mock import patch
        report = self.upload().json()
        path = f'/api/sessions/{report["session_id"]}'
        legacy = {'status': 'passed_supported_checks', 'checks': [{'finding_id': report['findings'][0]['id'], 'removed': True}]}
        with patch.object(engine, 'redact', return_value=(engine.sample_document(), legacy)):
            response = self.client.post(path + '/redact', headers=self.headers, json={'finding_ids': [report['findings'][0]['id']], 'approved': True})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(path + '/download', headers=self.headers).status_code, 409)


if __name__ == "__main__":
    unittest.main()
