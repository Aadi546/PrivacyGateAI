import hashlib
import time
import unittest

import fitz
from fastapi.testclient import TestClient

from backend import disclosure
from backend.main import app, receiver_app, SESSIONS, TOKEN


class PracticalTests(unittest.TestCase):
    def setUp(self):
        SESSIONS.clear()
        disclosure.GRANTS.clear()
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")
        self.receiver = TestClient(receiver_app, base_url="http://127.0.0.1:8766")
        self.headers = {"X-PrivacyGate-Token": TOKEN}

    def tearDown(self):
        self.client.close()
        self.receiver.close()
        SESSIONS.clear()
        disclosure.GRANTS.clear()

    def inspect(self, kind="identity", mode="cross_origin"):
        data, mime = disclosure.sample(kind)
        response = self.client.post("/api/analyze", headers=self.headers, files={"file": (disclosure.SAMPLES[kind][0], data, mime)})
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        sid = report["session_id"]
        context = self.client.post(f"/api/practical/sessions/{sid}/context", headers=self.headers, json={"mode": mode})
        self.assertEqual(context.status_code, 200, context.text)
        return data, report, context.json()

    def protect(self, report, ids=None):
        sid = report["session_id"]
        ids = [f["id"] for f in report["findings"]] if ids is None else ids
        return self.client.post(f"/api/practical/sessions/{sid}/protect", headers=self.headers,
                                json={"finding_ids": ids, "remove_metadata": True, "approved": True})

    def grant(self, report, mode="cross_origin", variant="original"):
        response = self.client.post(f'/api/practical/sessions/{report["session_id"]}/upload-approval', headers=self.headers,
                                   json={"mode": mode, "variant": variant, "approved": True})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_real_metadata_inspection_masks_values_and_keeps_destination_pending(self):
        _, report, context = self.inspect()
        self.assertIn("pdf.author", [f["id"] for f in context["hidden_information"]["findings"]])
        self.assertNotIn("Sample Applicant", str(context))
        self.assertIsNone(context["recipient"]["observed_destination"])
        self.assertEqual(context["recipient"]["origin_comparison"], "cross_origin")

    def test_combined_protection_is_real_and_original_is_unchanged(self):
        data, report, _ = self.inspect()
        response = self.protect(report)
        self.assertEqual(response.status_code, 200, response.text)
        proof = response.json()["verification"]
        self.assertEqual(proof["status"], "passed_supported_checks")
        self.assertTrue(proof["metadata_removed"])
        self.assertTrue(proof["original_unchanged"])
        output = self.client.get(f'/api/practical/sessions/{report["session_id"]}/download', headers=self.headers)
        self.assertEqual(output.status_code, 200)
        with fitz.open(stream=output.content, filetype="pdf") as doc:
            self.assertFalse(doc.metadata["author"])
            self.assertNotIn("2345 6789", doc[0].get_text())
            self.assertIn("0124", doc[0].get_text())
        self.assertEqual(SESSIONS[report["session_id"]].original, data)

    def test_metadata_only_cleanup_has_a_positive_verification_gate(self):
        _, report, _ = self.inspect()
        response = self.protect(report, [])
        self.assertEqual(response.status_code, 200, response.text)
        proof = response.json()["verification"]
        self.assertFalse(proof["pii_requested"])
        self.assertTrue(proof["metadata_removed"])
        self.assertEqual(proof["checks"], [])
        sid = report["session_id"]
        self.assertEqual(self.client.get(f"/api/practical/sessions/{sid}/download", headers=self.headers).status_code, 200)
        # The original extension's PII-only gate remains strict.
        self.assertEqual(self.client.get(f"/api/sessions/{sid}/download", headers=self.headers).status_code, 409)
        SESSIONS[sid].report["practical_verification"]["metadata_removed"] = False
        self.assertEqual(self.client.get(f"/api/practical/sessions/{sid}/download", headers=self.headers).status_code, 409)

    def test_jpeg_exif_is_detected_then_removed_from_fresh_png(self):
        _, report, context = self.inspect("photo")
        self.assertIn("exif.34853", [f["id"] for f in context["hidden_information"]["findings"]])
        response = self.protect(report, [])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["verification"]["mime"], "image/png")
        self.assertTrue(response.json()["verification"]["metadata_removed"])

    def test_both_recipient_origins_receive_matching_bytes_and_grant_is_single_use(self):
        for mode in ("same_origin", "cross_origin"):
            SESSIONS.clear()
            data, report, _ = self.inspect(mode=mode)
            grant = self.grant(report, mode)
            client = self.client if mode == "same_origin" else self.receiver
            headers = {"Origin": "http://127.0.0.1:8765", "X-PrivacyGate-Upload-Grant": grant["grant"], "Content-Type": "application/octet-stream"}
            response = client.post("/mock-upload", headers=headers, content=data)
            self.assertEqual(response.status_code, 200, response.text)
            receipt = response.json()
            self.assertEqual(receipt["bytes_received"], len(data))
            self.assertFalse(receipt["body_retained"])
            self.assertEqual(receipt["upload_id"], grant["upload_id"])
            stored = SESSIONS[report["session_id"]].report["recipient"]
            self.assertEqual(stored["observed_destination"], grant["upload_url"])
            self.assertEqual(client.post("/mock-upload", headers=headers, content=data).status_code, 403)

    def test_unapproved_expired_mismatched_and_tampered_uploads_are_rejected(self):
        data, report, _ = self.inspect()
        sid = report["session_id"]
        unapproved = self.client.post(f"/api/practical/sessions/{sid}/upload-approval", headers=self.headers,
                                     json={"variant": "original", "approved": False})
        self.assertEqual(unapproved.status_code, 400)
        self.assertEqual(self.receiver.post("/mock-upload", headers={"Origin": "http://127.0.0.1:8765"}, content=data).status_code, 403)
        grant = self.grant(report)
        disclosure.GRANTS[grant["grant"]]["expires"] = time.monotonic() - 1
        headers = {"Origin": "http://127.0.0.1:8765", "X-PrivacyGate-Upload-Grant": grant["grant"]}
        self.assertEqual(self.receiver.post("/mock-upload", headers=headers, content=data).status_code, 403)
        grant = self.grant(report)
        headers["X-PrivacyGate-Upload-Grant"] = grant["grant"]
        self.assertEqual(self.client.post("/mock-upload", headers=headers, content=data).status_code, 403)
        grant = self.grant(report)
        headers["X-PrivacyGate-Upload-Grant"] = grant["grant"]
        self.assertEqual(self.receiver.post("/mock-upload", headers=headers, content=data+b"tampered").status_code, 400)

    def test_signed_document_and_missing_protection_approval_are_blocked(self):
        _, report, _ = self.inspect("signed")
        self.assertEqual(self.protect(report, []).status_code, 422)
        response = self.client.post(f'/api/practical/sessions/{report["session_id"]}/protect', headers=self.headers,
                                    json={"finding_ids": [], "approved": False, "remove_metadata": True})
        self.assertEqual(response.status_code, 400)

    def test_changed_context_invalidates_grants_and_tampered_output_blocks_download(self):
        _, report, _ = self.inspect()
        grant = self.grant(report)
        sid = report["session_id"]
        self.client.post(f"/api/practical/sessions/{sid}/context", headers=self.headers, json={"mode": "same_origin"})
        self.assertNotIn(grant["grant"], disclosure.GRANTS)
        self.protect(report)
        SESSIONS[sid].output += b"tampered"
        self.assertEqual(self.client.get(f"/api/practical/sessions/{sid}/download", headers=self.headers).status_code, 409)

    def test_external_origins_and_unknown_destinations_are_rejected(self):
        _, report, _ = self.inspect()
        self.assertEqual(self.receiver.options("/mock-upload", headers={"Origin": "https://unrelated.example"}).status_code, 403)
        response = self.client.post(f'/api/practical/sessions/{report["session_id"]}/context', headers=self.headers,
                                    json={"page_origin": "https://unrelated.example", "mode": "cross_origin"})
        self.assertEqual(response.status_code, 422)
